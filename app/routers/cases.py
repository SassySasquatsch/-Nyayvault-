from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.abac import Action, filter_visible_cases, get_authorised_case, scope_for_new_case
from app.config import settings
from app.database import get_db
from app.dependencies import get_client_ip, get_current_user, log_audit, require_roles
from app.models import AuditAction, AuditLog, Case, CaseStatus, Signature, SignaturePurpose, User
from app.schemas import CaseCloseResult, CaseCreate, CaseDetailOut, CaseOut, OverviewOut, PresentSessionOut
from app.utils.hashing import sha256_of_bytes
from app.utils.signing import SigningError, sign_hash

router = APIRouter(prefix="/api/cases", tags=["cases"])


def _last_activity(db: Session, case_ids: list) -> dict:
    """{case_id: latest audit timestamp}. Refused-access attempts are not
    'activity on the case', so they don't count."""
    if not case_ids:
        return {}
    rows = (
        db.query(AuditLog.case_id, func.max(AuditLog.timestamp))
        .filter(AuditLog.case_id.in_(case_ids), AuditLog.action != AuditAction.access_denied)
        .group_by(AuditLog.case_id)
        .all()
    )
    return dict(rows)


def _serialize(db: Session, cases: list, model=CaseOut) -> list:
    last = _last_activity(db, [c.id for c in cases])
    # a case that has no audit events yet (e.g. seeded) was last "active" when it was opened
    return [model.model_validate(c).model_copy(update={"last_activity": last.get(c.id) or c.created_at}) for c in cases]


@router.get("", response_model=list[CaseOut])
def list_cases(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Every approved role can list cases, but ABAC narrows the list to the
    cases the caller is authorised for and whose organisational scope matches
    theirs. For an IO that is 'My Cases'."""
    cases = db.query(Case).order_by(Case.created_at.desc()).all()
    return _serialize(db, filter_visible_cases(user, cases, Action.CASE_LIST))


@router.post("", response_model=CaseOut, status_code=201)
def create_case(
    payload: CaseCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("io")),
):
    if db.query(Case).filter(Case.number == payload.number).first():
        raise HTTPException(400, "A case with this FIR number already exists.")

    # ABAC: the creating IO becomes the owner and the case is stamped with
    # their organisational scope. Neither comes from the request body, so an
    # officer cannot open a case in someone else's state/district/unit.
    scope = scope_for_new_case(user)

    case = Case(
        number=payload.number,
        title=payload.title,
        status=payload.status,
        created_by_id=user.id,
        owner_id=user.id,
        **scope,
    )
    db.add(case)
    db.commit()
    db.refresh(case)

    log_audit(
        db,
        action=AuditAction.case_create,
        detail=f"'{user.username}' opened case {case.number} — {case.title}",
        user=user,
        ip_address=get_client_ip(request),
        case_id=case.id,
    )
    return _serialize(db, [case])[0]


@router.get("/overview/summary", response_model=OverviewOut)
def overview(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.models import Document, DocStatus, CaseStatus

    # Counts cover only what the caller may see (ABAC), never other orgs' data.
    cases = filter_visible_cases(user, db.query(Case).all(), Action.CASE_LIST)
    ids = [c.id for c in cases]
    active_cases = sum(1 for c in cases if c.status == CaseStatus.active)
    pending = evidence_items = audit_events = 0
    if ids:
        pending = db.query(Document).filter(Document.case_id.in_(ids), Document.status != DocStatus.verified).count()
        evidence_items = db.query(Document).filter(Document.case_id.in_(ids)).count()
        audit_events = db.query(AuditLog).filter(AuditLog.case_id.in_(ids)).count()
    if (user.role.value if hasattr(user.role, "value") else user.role) in settings.ABAC_ORG_WIDE_ROLES:
        audit_events = db.query(AuditLog).count()   # oversight roles keep the global count
    return OverviewOut(
        active_cases=active_cases,
        pending_verification=pending,
        evidence_items=evidence_items,
        audit_events=audit_events,
    )


@router.get("/{case_id}", response_model=CaseDetailOut)
def get_case(
    case_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    case = get_authorised_case(db, user, case_id, Action.CASE_READ, request=request)
    return _serialize(db, [case], CaseDetailOut)[0]

@router.post("/{case_id}/present", response_model=PresentSessionOut)
def present_in_court(
    case_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("judge")),
):
    """Logs (and timestamps) a courtroom presentation session. The frontend
    renders the watermark client-side; the backend is the source of truth
    for who presented what, and when, for the audit trail."""
    case = get_authorised_case(db, user, case_id, Action.CASE_PRESENT, request=request)

    now = datetime.now(timezone.utc)
    watermark = f"PRESENTED BY {user.username.upper()} · {user.role_label.upper()}"

    log_audit(
        db,
        action=AuditAction.present,
        detail=f"'{user.username}' presented case {case.number} in courtroom view",
        user=user,
        ip_address=get_client_ip(request),
        case_id=case.id,
    )
    return PresentSessionOut(
        case_id=case.id, watermark_text=watermark, presented_by=user.full_name, presented_at=now
    )


@router.post("/{case_id}/close", response_model=CaseCloseResult)
def close_case(
    case_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("judge")),
):
    """
    Judge closes a case. There is no underlying file to hash here (unlike
    a forensic report or court order upload), so a canonical, deterministic
    description of the closure event is hashed instead
    (app/utils/hashing.sha256_of_bytes -- never the file-hashing path in
    sha256_of_file, which stays untouched) and that hash is what gets
    digitally signed with the judge's own key, for the same non-repudiation
    reason a report or order is signed: so that *this specific judge*
    closed *this specific case* at *this specific time* can later be proven
    independent of the app's own say-so.

    Non-repudiation here is additive, exactly like everywhere else in this
    feature: if the judge has no signing key, or the 'cryptography' library
    isn't installed, the case still closes -- it is simply left unsigned,
    and that is recorded plainly in the audit log rather than hidden.
    """
    case = get_authorised_case(db, user, case_id, Action.CASE_CLOSE, request=request)
    if case.status == CaseStatus.closed:
        raise HTTPException(400, f"Case {case.number} is already closed.")

    now = datetime.now(timezone.utc)
    case.status = CaseStatus.closed
    db.commit()
    db.refresh(case)

    # Canonical closure statement: stable, unambiguous, and tied to this
    # exact case + judge + moment -- not the whole Case row (which would
    # make the signed statement drift every time an unrelated column on the
    # case changes).
    statement = (
        f"CASE_CLOSURE|case_id={case.id}|case_number={case.number}|"
        f"closed_by={user.id}|closed_at={now.isoformat()}"
    ).encode("utf-8")
    closure_hash = sha256_of_bytes(statement)

    log_audit(
        db,
        action=AuditAction.case_close,
        detail=f"'{user.username}' closed case {case.number}",
        user=user,
        ip_address=get_client_ip(request),
        case_id=case.id,
    )

    signature_out = None
    if not user.private_key_encrypted_pem:
        log_audit(
            db,
            action=AuditAction.sign,
            detail=f"No signature produced for the closure of {case.number}: '{user.username}' has no signing key on file.",
            user=user,
            case_id=case.id,
        )
    else:
        try:
            result = sign_hash(user.private_key_encrypted_pem, closure_hash)
        except SigningError as exc:
            log_audit(
                db,
                action=AuditAction.sign,
                detail=f"No signature produced for the closure of {case.number}: {exc}",
                user=user,
                case_id=case.id,
            )
        else:
            signature = Signature(
                case_id=case.id,
                signer_user_id=user.id,
                purpose=SignaturePurpose.case_closure,
                signed_hash=closure_hash,
                signature=result.signature_b64,
                algorithm=result.algorithm,
            )
            db.add(signature)
            db.commit()
            db.refresh(signature)
            log_audit(
                db,
                action=AuditAction.sign,
                detail=f"'{user.username}' digitally signed the closure of {case.number} ({result.algorithm})",
                user=user,
                case_id=case.id,
            )
            from app.schemas import SignatureOut
            signature_out = SignatureOut.model_validate(signature)

    return CaseCloseResult(case=_serialize(db, [case])[0], signature=signature_out)
