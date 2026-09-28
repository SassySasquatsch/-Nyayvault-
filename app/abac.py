"""
Lightweight ABAC + organisational segregation.

This is a *second gate on top of* the existing RBAC, not a replacement for it.
Every protected request now passes three checks, in this order:

  1. ROLE      the user's role permits the action.
               Unchanged: the existing `require_roles(...)` dependency on each
               endpoint. There is no second role table here.
  2. SCOPE     the user's organisational attributes (state / district / unit)
               match the resource's. "*" on the user side = every value at
               that level. A missing (NULL) attribute on either side denies:
               the policy fails closed.
  3. ASSIGNED  for roles listed in ABAC_ASSIGNMENT_ROLES (default: io) the
               user must also be the case's owner / assigned officer.

Roles in ABAC_ORG_WIDE_ROLES (default: admin) skip 2 and 3 - they are system
oversight accounts - but they still go through the document-type rule.

Attributes used
  user      role, id, state, district, unit
  resource  case owner_id, state, district, unit, case id, document id,
            document type, requested action
Documents and evidence inherit their organisational scope from their case,
so there is exactly one place a resource's scope is stored.

Nothing here names a state, district or unit. Which attributes are enforced
and which roles are exempt / assignment-bound is configuration
(app/config.py: ABAC_*). Sample orgs live only in seed_data.py.

Historical audit / lifecycle events stay read-only for everyone: the action
vocabulary below has no write action for them, no such route exists, and
app/utils/audit_guard.py makes the ORM refuse UPDATE/DELETE on audit_logs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_client_ip, log_audit
from app.models import AuditAction, Case, Document, User

WILDCARD = "*"
_SCOPE_COLUMNS = ("state", "district", "unit")   # columns that exist on users AND cases


class Action:
    """Action vocabulary. Read-only for audit/lifecycle - by design there is
    nothing here that could modify history."""
    CASE_LIST = "case:list"
    CASE_READ = "case:read"
    CASE_CREATE = "case:create"
    CASE_PRESENT = "case:present"
    CASE_REPORT = "case:report"
    CASE_LIFECYCLE = "case:lifecycle"      # read-only
    CASE_AUDIT = "case:audit"              # read-only
    DOC_LIST = "doc:list"
    DOC_READ = "doc:read"
    DOC_UPLOAD = "doc:upload"
    DOC_UPLOAD_FORENSIC_REPORT = "doc:upload_forensic_report"
    DOC_UPLOAD_COURT_ORDER = "doc:upload_court_order"
    DOC_DOWNLOAD = "doc:download"
    DOC_VERIFY = "doc:verify"
    DOC_SIGNATURE_VERIFY = "doc:signature_verify"
    DOC_BLOCKCHAIN = "doc:blockchain"
    DOC_REDACT = "doc:redact"
    DOC_TRANSCRIBE = "doc:transcribe"
    CASE_CLOSE = "case:close"
    SEARCH = "search"


def _validate_config() -> tuple:
    attrs = tuple(settings.ABAC_SCOPE_ATTRIBUTES)
    bad = [a for a in attrs if a not in _SCOPE_COLUMNS]
    if bad:
        raise RuntimeError(
            f"ABAC_SCOPE_ATTRIBUTES contains unsupported attribute(s) {bad}; "
            f"choose from {list(_SCOPE_COLUMNS)}."
        )
    return attrs


SCOPE_ATTRIBUTES = _validate_config()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _role(user: User) -> str:
    return user.role.value if hasattr(user.role, "value") else user.role


def _norm(value) -> Optional[str]:
    """Case/whitespace-insensitive comparison key; blank -> None."""
    if value is None:
        return None
    v = str(value).strip().casefold()
    return v or None


def describe_scope(obj) -> str:
    """'Uttarakhand / Dehradun / Unit A' (for audit text and the UI)."""
    return " / ".join((getattr(obj, a, None) or "—") for a in SCOPE_ATTRIBUTES)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""      # detailed - goes to the audit log only
    code: str = ""        # "scope" | "assignment" | "doc_type" | ""


_PUBLIC_MESSAGES = {
    "scope": "Access denied: this resource is outside your organisational scope.",
    "assignment": "Access denied: this case is not assigned to you.",
    "doc_type": "Access denied: your role may not access this document type.",
}


# ---------------------------------------------------------------------------
# the policy
# ---------------------------------------------------------------------------
def evaluate(user: User, case: Case, action: str, document: Optional[Document] = None) -> Decision:
    role = _role(user)

    # A document must belong to the case it is being authorised through.
    if document is not None and document.case_id != case.id:
        return Decision(False, "document does not belong to this case", "scope")

    # Document-type attribute (optional, per-role, configuration-driven).
    if document is not None:
        allowed_types = settings.ABAC_ROLE_DOC_TYPES.get(role)
        doc_type = document.type.value if hasattr(document.type, "value") else document.type
        if allowed_types is not None and doc_type not in {str(t).upper() for t in allowed_types}:
            return Decision(False, f"role '{role}' may not act on {doc_type} documents", "doc_type")

    if role in settings.ABAC_ORG_WIDE_ROLES:
        return Decision(True)

    # Organisational scope.
    for attr in SCOPE_ATTRIBUTES:
        u = _norm(getattr(user, attr, None))
        if u is None:
            return Decision(False, f"user has no '{attr}' attribute", "scope")
        if u == WILDCARD:
            continue
        r = _norm(getattr(case, attr, None))
        if r is None or r != u:
            return Decision(False, f"{attr} mismatch", "scope")

    # Case assignment.
    if role in settings.ABAC_ASSIGNMENT_ROLES and case.owner_id != user.id:
        return Decision(False, "case is not assigned to this user", "assignment")

    return Decision(True)


# ---------------------------------------------------------------------------
# enforcement helpers used by the routers
# ---------------------------------------------------------------------------
def _log_denial(db: Session, user: User, case: Case, action: str, decision: Decision,
                request: Optional[Request], document: Optional[Document]) -> None:
    """Best effort: a failure to write the audit row must never turn a clean
    403 into a 500."""
    try:
        log_audit(
            db,
            action=AuditAction.access_denied,
            detail=(
                f"ABAC denied '{user.username}' ({_role(user)}, {describe_scope(user)}) "
                f"action '{action}' on case {case.number} ({describe_scope(case)}): {decision.reason}"
            ),
            user=user,
            ip_address=get_client_ip(request) if request is not None else None,
            case_id=case.id,
            document_id=document.id if document is not None else None,
        )
    except Exception:  # noqa: BLE001
        db.rollback()


def require_case_access(db: Session, user: User, case: Case, action: str, *,
                        request: Optional[Request] = None,
                        document: Optional[Document] = None) -> Case:
    decision = evaluate(user, case, action, document)
    if not decision.allowed:
        _log_denial(db, user, case, action, decision, request, document)
        raise HTTPException(status.HTTP_403_FORBIDDEN, _PUBLIC_MESSAGES.get(decision.code, "Access denied."))
    return case


def get_authorised_case(db: Session, user: User, case_id: str, action: str, *,
                        request: Optional[Request] = None) -> Case:
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(404, "Case not found.")
    return require_case_access(db, user, case, action, request=request)


def get_authorised_document(db: Session, user: User, document_id: str, action: str, *,
                            request: Optional[Request] = None) -> Document:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found.")
    if doc.case is None:
        raise HTTPException(404, "Document not found.")
    require_case_access(db, user, doc.case, action, request=request, document=doc)
    return doc


def can_access_case(user: User, case: Case, action: str = Action.CASE_READ) -> bool:
    return evaluate(user, case, action).allowed


def filter_visible_cases(user: User, cases: Iterable[Case], action: str = Action.CASE_LIST) -> list:
    """List/search endpoints don't 403 - they simply omit what the caller
    may not see. Uses the same `evaluate` as everything else, so there is one
    definition of 'may access' (fine at prototype scale)."""
    return [c for c in cases if evaluate(user, c, action).allowed]


def scope_for_new_case(user: User) -> dict:
    """Organisational scope stamped on a case the user creates: the creating
    officer's own scope, never client-supplied. Wildcard / missing attributes
    cannot be stamped on a case."""
    out = {}
    for col in _SCOPE_COLUMNS:
        v = (getattr(user, col, None) or "").strip()
        if v and v != WILDCARD:
            out[col] = v
        elif col in SCOPE_ATTRIBUTES:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Your account has no specific '{col}' set, so it cannot open cases. "
                "Ask an administrator to set your organisational scope.",
            )
    return out
