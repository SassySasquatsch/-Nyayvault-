from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.abac import Action, get_authorised_case, get_authorised_document
from app.config import settings
from app.database import SessionLocal, get_db
from app.dependencies import get_client_ip, get_current_user, log_audit, require_roles
from app.models import AuditAction, AuditLog, Case, DocStatus, DocType, Document, Signature, SignaturePurpose, User
from app.schemas import DocumentOut, SignatureVerifyResult, VerifyResult
from app.utils.blockchain_anchor import AlreadyAnchoredError, BlockchainAnchorError, anchor_hash_to_blockchain
from app.utils.doc_category import (
    COURT_ORDER_EXTENSIONS,
    DOC_CATEGORY_COURT_ORDER,
    DOC_CATEGORY_EVIDENCE,
    DOC_CATEGORY_FORENSIC_REPORT,
    FORENSIC_REPORT_EXTENSIONS,
    has_court_order_extension,
    has_forensic_report_extension,
)
from app.utils.exif_utils import classify_doc_type, extract_metadata
from app.utils.hashing import sha256_of_file
from app.utils.ocr_utils import extract_searchable_text, needs_ocr
from app.utils.pdf_report import stamp_pdf_watermark
from app.utils.signing import SigningError, sign_hash, verify_signature

router = APIRouter(prefix="/api/documents", tags=["documents"])
cases_router = APIRouter(prefix="/api/cases", tags=["documents"])

MAX_UPLOAD_BYTES = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024


def _anchor_hash_in_background(document_id: str, case_id: str, sha256_hex: str) -> None:
    """
    Runs *after* the upload response has already been sent (see
    `background_tasks.add_task(...)` below). Deliberately isolated from the
    request lifecycle:

      - Opens its own short-lived DB session -- the request-scoped one from
        Depends(get_db) is already closed by the time this runs.
      - Never raises. A slow or unreachable blockchain node can delay when
        `blockchain_tx_hash` gets filled in, but it can never fail, slow
        down, or roll back the upload itself, and it never touches file
        storage.
      - Writes exactly one audit log row recording the outcome (success,
        already-anchored, or skipped/failed), same as every other action in
        this app.
    """
    db = SessionLocal()
    try:
        try:
            tx_hash = anchor_hash_to_blockchain(sha256_hex)
        except AlreadyAnchoredError as exc:
            db.add(AuditLog(
                action=AuditAction.blockchain_anchor,
                detail=f"Hash for document {document_id} was already anchored on-chain: {exc}",
                case_id=case_id,
                document_id=document_id,
            ))
            db.commit()
            return
        except BlockchainAnchorError as exc:
            db.add(AuditLog(
                action=AuditAction.blockchain_anchor_failed,
                detail=f"Blockchain anchoring skipped for document {document_id}: {exc}",
                case_id=case_id,
                document_id=document_id,
            ))
            db.commit()
            return

        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.blockchain_tx_hash = tx_hash
        from app.utils.blockchain_anchor import get_explorer_tx_url
        explorer_url = get_explorer_tx_url(tx_hash)
        detail = f"Hash for document {document_id} anchored on-chain (tx {tx_hash})"
        if explorer_url:
            detail += f" -- {explorer_url}"
        db.add(AuditLog(
            action=AuditAction.blockchain_anchor,
            detail=detail,
            case_id=case_id,
            document_id=document_id,
        ))
        db.commit()
    finally:
        db.close()


def _extract_ocr_in_background(document_id: str, case_id: str, file_path: Path, doc_type: str) -> None:
    """
    Runs *after* the upload response has already been sent (see
    `background_tasks.add_task(...)` below) -- same isolation pattern as
    `_anchor_hash_in_background` above:

      - Opens its own short-lived DB session.
      - Never raises. Tesseract/poppler being slow, missing, or choking on a
        bad scan can delay when `ocr_text`/`ocr_method` get filled in, but it
        can never fail, slow down, or roll back the upload itself, and it
        never writes to the evidence file on disk.
      - Writes exactly one audit log row recording the outcome, same as
        every other action in this app.

    Once `ocr_text` is set, it's picked up automatically by `/api/search`
    (see app/routers/search.py) -- no separate indexing step needed.
    """
    db = SessionLocal()
    try:
        text, method = extract_searchable_text(file_path, doc_type)

        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.ocr_text = text
            doc.ocr_method = method

        if text:
            chars = len(text)
            detail = f"Extracted {chars} characters of searchable text from document {document_id} (method: {method})"
        else:
            detail = (
                f"No searchable text extracted for document {document_id} -- no usable text layer "
                "and OCR unavailable or found nothing on this file"
            )
        db.add(AuditLog(
            action=AuditAction.ocr_extract,
            detail=detail,
            case_id=case_id,
            document_id=document_id,
        ))
        db.commit()
    except Exception:
        # Best-effort background enhancement -- must never surface as a
        # failed upload, and there's no request left to report it to anyway.
        db.rollback()
    finally:
        db.close()


def _sign_document(db: Session, document: Document, signer: User, purpose: SignaturePurpose) -> Optional[Signature]:
    """
    Signs a document's existing SHA-256 (Document.hash_sha256 -- never
    recomputed here, see app/utils/hashing.py) with the signer's own
    private key, stores the result as a Signature row, and logs it via the
    same log_audit() every other action uses. Called synchronously (unlike
    blockchain anchoring): signing is local CPU work with no network call,
    so there's no reason to defer it to a background task, and the caller
    can immediately return the signature status to the client.

    Never raises, and never blocks the upload/action it's attached to: if
    the signer has no keypair yet, or the 'cryptography' library isn't
    installed, this logs a `sign` audit entry explaining that no signature
    was produced and returns None -- exactly the same "degrade gracefully,
    never fabricate" posture as app/utils/blockchain_anchor.py.
    """
    if not signer.private_key_encrypted_pem:
        log_audit(
            db,
            action=AuditAction.sign,
            detail=(
                f"No signature produced for {document.name}: '{signer.username}' has no signing key on file."
            ),
            user=signer,
            case_id=document.case_id,
            document_id=document.id,
        )
        return None

    try:
        result = sign_hash(signer.private_key_encrypted_pem, document.hash_sha256)
    except SigningError as exc:
        log_audit(
            db,
            action=AuditAction.sign,
            detail=f"No signature produced for {document.name}: {exc}",
            user=signer,
            case_id=document.case_id,
            document_id=document.id,
        )
        return None

    signature = Signature(
        document_id=document.id,
        signer_user_id=signer.id,
        purpose=purpose,
        signed_hash=document.hash_sha256,
        signature=result.signature_b64,
        algorithm=result.algorithm,
    )
    db.add(signature)
    db.commit()
    db.refresh(signature)

    log_audit(
        db,
        action=AuditAction.sign,
        detail=(
            f"'{signer.username}' digitally signed {document.name} "
            f"(SHA-256 {document.hash_sha256}, {result.algorithm})"
        ),
        user=signer,
        case_id=document.case_id,
        document_id=document.id,
    )
    return signature


async def _write_upload(file: UploadFile, dest_path: Path) -> int:
    """Stream an upload to disk in 1 MB chunks, enforcing the size limit.
    Returns the number of bytes written; removes the partial file on failure."""
    size = 0
    with open(dest_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                out.close()
                dest_path.unlink(missing_ok=True)
                raise HTTPException(
                    413, f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB}MB upload limit."
                )
            out.write(chunk)
    return size


@cases_router.get("/{case_id}/documents", response_model=list[DocumentOut])
def list_case_documents(
    case_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    case = get_authorised_case(db, user, case_id, Action.DOC_LIST, request=request)
    return case.documents


@cases_router.post("/{case_id}/documents", response_model=DocumentOut, status_code=201)
async def upload_document(
    case_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("io", "forensic")),
    file: UploadFile = File(...),
):
    # ABAC: checked before a single byte of the upload is read or written.
    case = get_authorised_case(db, user, case_id, Action.DOC_UPLOAD, request=request)

    doc_type = classify_doc_type(file.filename, file.content_type)

    case_dir: Path = settings.EVIDENCE_DIR / case.id
    case_dir.mkdir(parents=True, exist_ok=True)

    # Namespace the file on disk so two uploads with the same filename never
    # collide, while keeping the human-readable name for display/reports.
    from app.models import gen_id

    doc_id = gen_id("doc")
    safe_name = Path(file.filename).name
    dest_path = case_dir / f"{doc_id}__{safe_name}"

    size = await _write_upload(file, dest_path)

    file_hash = sha256_of_file(dest_path)
    metadata = extract_metadata(dest_path, doc_type)

    document = Document(
        id=doc_id,
        case_id=case.id,
        name=safe_name,
        category=DOC_CATEGORY_EVIDENCE,
        type=doc_type,
        file_path=str(dest_path.relative_to(settings.STORAGE_DIR)),
        size_bytes=size,
        content_type=file.content_type,
        uploader_id=user.id,
        hash_sha256=file_hash,
        status=DocStatus.verified,  # hash captured fresh at upload time
        last_verified_at=datetime.now(timezone.utc),
        exif=metadata,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    log_audit(
        db,
        action=AuditAction.upload,
        detail=f"'{user.username}' uploaded {document.name} to {case.number}",
        user=user,
        ip_address=get_client_ip(request),
        case_id=case.id,
        document_id=document.id,
    )

    # Fire-and-forget: scheduled to run after this response is sent, on its
    # own DB session. Anchoring status/tx_hash is picked up whenever the
    # document is next fetched (GET /api/documents/{id}) -- the upload
    # response itself never waits on the chain.
    background_tasks.add_task(
        _anchor_hash_in_background, document.id, case.id, document.hash_sha256
    )

    # Scanned PDFs (no text layer) and image uploads (.png/.jpg/...) get run
    # through OCR in the background so their content becomes searchable via
    # /api/search -- see app/utils/ocr_utils.py. Runs after the response is
    # sent, same as blockchain anchoring above; never delays or fails the
    # upload itself.
    if needs_ocr(doc_type):
        background_tasks.add_task(
            _extract_ocr_in_background, document.id, case.id, dest_path, doc_type
        )

    return document


@cases_router.get("/{case_id}/forensic-reports", response_model=list[DocumentOut])
def list_forensic_reports(
    case_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Forensic reports of one case. Same access rule as the case's other
    documents: an approved user whose organisational scope matches the case
    (and, for an IO, who owns it). Everyone else gets 403 + an audit event."""
    case = get_authorised_case(db, user, case_id, Action.DOC_LIST, request=request)
    return [d for d in case.documents if d.category == DOC_CATEGORY_FORENSIC_REPORT]


@cases_router.post("/{case_id}/forensic-reports", response_model=DocumentOut, status_code=201)
async def upload_forensic_report(
    case_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("forensic")),
    file: UploadFile = File(...),
):
    """Forensic officer uploads an examination report (PDF / DOC / DOCX).

    Reuses the evidence pipeline: the SHA-256 is generated server-side and
    stored with the uploader and timestamp, an audit event is written (which is
    what puts it on the case's document lifecycle), and the hash is anchored on
    the blockchain in the background when anchoring is enabled. Access to the
    stored file afterwards is the normal RBAC + ABAC document access
    (GET /api/documents/{id}, /download, /verify)."""
    # RBAC (require_roles above) + ABAC: checked before a byte is read.
    case = get_authorised_case(db, user, case_id, Action.DOC_UPLOAD_FORENSIC_REPORT, request=request)

    if not file.filename or not file.filename.strip():
        raise HTTPException(400, "A file is required.")
    safe_name = Path(file.filename.replace("\\", "/")).name
    if not has_forensic_report_extension(safe_name):
        raise HTTPException(
            400,
            "A forensic report must be a "
            + ", ".join(e.lstrip(".").upper() for e in FORENSIC_REPORT_EXTENSIONS)
            + " file.",
        )

    from app.models import gen_id

    case_dir: Path = settings.FORENSIC_REPORTS_DIR / case.id
    case_dir.mkdir(parents=True, exist_ok=True)
    doc_id = gen_id("doc")
    dest_path = case_dir / f"{doc_id}__{safe_name}"

    size = await _write_upload(file, dest_path)
    if size == 0:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(400, "The uploaded file is empty.")

    doc_type = classify_doc_type(safe_name, file.content_type)
    file_hash = sha256_of_file(dest_path)
    metadata = extract_metadata(dest_path, doc_type)

    document = Document(
        id=doc_id,
        case_id=case.id,
        name=safe_name,
        category=DOC_CATEGORY_FORENSIC_REPORT,
        type=doc_type,
        file_path=str(dest_path.relative_to(settings.STORAGE_DIR)),
        size_bytes=size,
        content_type=file.content_type,
        uploader_id=user.id,
        hash_sha256=file_hash,
        status=DocStatus.verified,  # hash captured fresh at upload time
        last_verified_at=datetime.now(timezone.utc),
        exif=metadata,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    log_audit(
        db,
        action=AuditAction.forensic_report_upload,
        detail=(
            f"'{user.username}' uploaded forensic report {document.name} to {case.number} "
            f"(SHA-256 {file_hash})"
        ),
        user=user,
        ip_address=get_client_ip(request),
        case_id=case.id,
        document_id=document.id,
    )

    # Non-repudiation: the forensic officer signs their own report's hash
    # with their own private key, so authorship can later be proven
    # independent of the app's own say-so. Never blocks or fails the
    # upload -- see _sign_document above.
    _sign_document(db, document, user, SignaturePurpose.forensic_report)

    background_tasks.add_task(
        _anchor_hash_in_background, document.id, case.id, document.hash_sha256
    )

    # Forensic reports are PDF/DOC/DOCX (see FORENSIC_REPORT_EXTENSIONS) --
    # a scanned/signed-and-scanned PDF report with no text layer gets OCR'd
    # in the background exactly like an evidence upload above.
    if needs_ocr(doc_type):
        background_tasks.add_task(
            _extract_ocr_in_background, document.id, case.id, dest_path, doc_type
        )
    return document


@cases_router.get("/{case_id}/court-orders", response_model=list[DocumentOut])
def list_court_orders(
    case_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Court orders / judgments uploaded to one case. Same access rule as
    the case's other documents."""
    case = get_authorised_case(db, user, case_id, Action.DOC_LIST, request=request)
    return [d for d in case.documents if d.category == DOC_CATEGORY_COURT_ORDER]


@cases_router.post("/{case_id}/court-orders", response_model=DocumentOut, status_code=201)
async def upload_court_order(
    case_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("judge")),
    file: UploadFile = File(...),
):
    """Judge uploads a court order / judgment (PDF / DOC / DOCX).

    Same shape as upload_forensic_report above: the SHA-256 is generated
    server-side, an audit event is written, and the judge's own signature
    is produced over that hash (see _sign_document) so the order can later
    be proven to have come from that judge and be unaltered since. This is
    independent of case closure -- a court order can be filed without the
    case being closed, and app/routers/cases.py close_case does not require
    one on file. Access to the stored file afterwards is the normal
    RBAC + ABAC document access (GET /api/documents/{id}, /download,
    /signature/verify)."""
    # RBAC (require_roles above) + ABAC: checked before a byte is read.
    case = get_authorised_case(db, user, case_id, Action.DOC_UPLOAD_COURT_ORDER, request=request)

    if not file.filename or not file.filename.strip():
        raise HTTPException(400, "A file is required.")
    safe_name = Path(file.filename.replace("\\", "/")).name
    if not has_court_order_extension(safe_name):
        raise HTTPException(
            400,
            "A court order / judgment must be a "
            + ", ".join(e.lstrip(".").upper() for e in COURT_ORDER_EXTENSIONS)
            + " file.",
        )

    from app.models import gen_id

    case_dir: Path = settings.COURT_ORDERS_DIR / case.id
    case_dir.mkdir(parents=True, exist_ok=True)
    doc_id = gen_id("doc")
    dest_path = case_dir / f"{doc_id}__{safe_name}"

    size = await _write_upload(file, dest_path)
    if size == 0:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(400, "The uploaded file is empty.")

    doc_type = classify_doc_type(safe_name, file.content_type)
    file_hash = sha256_of_file(dest_path)
    metadata = extract_metadata(dest_path, doc_type)

    document = Document(
        id=doc_id,
        case_id=case.id,
        name=safe_name,
        category=DOC_CATEGORY_COURT_ORDER,
        type=doc_type,
        file_path=str(dest_path.relative_to(settings.STORAGE_DIR)),
        size_bytes=size,
        content_type=file.content_type,
        uploader_id=user.id,
        hash_sha256=file_hash,
        status=DocStatus.verified,  # hash captured fresh at upload time
        last_verified_at=datetime.now(timezone.utc),
        exif=metadata,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    log_audit(
        db,
        action=AuditAction.court_order_upload,
        detail=(
            f"'{user.username}' uploaded court order/judgment {document.name} to {case.number} "
            f"(SHA-256 {file_hash})"
        ),
        user=user,
        ip_address=get_client_ip(request),
        case_id=case.id,
        document_id=document.id,
    )

    # Non-repudiation: the judge signs the order/judgment's hash with their
    # own private key. Never blocks or fails the upload -- see
    # _sign_document above.
    _sign_document(db, document, user, SignaturePurpose.court_order)

    background_tasks.add_task(
        _anchor_hash_in_background, document.id, case.id, document.hash_sha256
    )

    if needs_ocr(doc_type):
        background_tasks.add_task(
            _extract_ocr_in_background, document.id, case.id, dest_path, doc_type
        )
    return document


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = get_authorised_document(db, user, document_id, Action.DOC_READ, request=request)

    log_audit(
        db,
        action=AuditAction.view,
        detail=f"'{user.username}' opened {doc.name}",
        user=user,
        ip_address=get_client_ip(request),
        case_id=doc.case_id,
        document_id=doc.id,
    )
    return doc


@router.get("/{document_id}/blockchain")
def get_blockchain_anchor_status(
    document_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Live, read-only chain lookup -- independent of the `blockchain_tx_hash`
    column, which just remembers the tx we sent. This calls the contract
    directly so the result can't drift from on-chain truth, and costs no
    gas (view call).
    """
    doc = get_authorised_document(db, user, document_id, Action.DOC_BLOCKCHAIN, request=request)

    from app.utils.blockchain_anchor import BlockchainAnchorError, get_anchor_record, get_explorer_tx_url

    explorer_url = get_explorer_tx_url(doc.blockchain_tx_hash)

    try:
        record = get_anchor_record(doc.hash_sha256)
    except BlockchainAnchorError as exc:
        return {
            "document_id": doc.id,
            "hash_sha256": doc.hash_sha256,
            "blockchain_tx_hash": doc.blockchain_tx_hash,
            "blockchain_explorer_url": explorer_url,
            "on_chain": None,
            "detail": str(exc),
        }

    return {
        "document_id": doc.id,
        "hash_sha256": doc.hash_sha256,
        "blockchain_tx_hash": doc.blockchain_tx_hash,
        "blockchain_explorer_url": explorer_url,
        "on_chain": {
            "anchored": record.exists,
            "anchored_by": record.anchored_by if record.exists else None,
            "timestamp": record.timestamp if record.exists else None,
        },
    }


@router.post("/{document_id}/verify", response_model=VerifyResult)
def verify_document(
    document_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("forensic")),
):
    """Recomputes the SHA-256 of the file currently on disk and compares it
    against the hash captured at upload time -- a real integrity check, not
    a simulated one."""
    doc = get_authorised_document(db, user, document_id, Action.DOC_VERIFY, request=request)

    file_path = settings.STORAGE_DIR / doc.file_path
    if not file_path.exists():
        raise HTTPException(410, "Evidence file is missing from storage.")

    current_hash = sha256_of_file(file_path)
    match = current_hash == doc.hash_sha256
    doc.status = DocStatus.verified if match else DocStatus.tampered
    doc.last_verified_at = datetime.now(timezone.utc)
    db.commit()

    log_audit(
        db,
        action=AuditAction.verify if match else AuditAction.tamper,
        detail=(
            f"Integrity check on {doc.name}: "
            + ("hash match, verified" if match else "HASH MISMATCH — possible tampering")
        ),
        user=user,
        ip_address=get_client_ip(request),
        case_id=doc.case_id,
        document_id=doc.id,
    )
    return VerifyResult(
        document_id=doc.id,
        status=doc.status,
        hash_at_upload=doc.hash_sha256,
        hash_now=current_hash,
        match=match,
        checked_at=doc.last_verified_at,
    )


@router.get("/{document_id}/signature/verify", response_model=SignatureVerifyResult)
def verify_document_signature(
    document_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Re-verifies a document's stored digital signature against the
    signer's stored public key and the file's *current* hash -- mirrors
    verify_document above (recompute, don't trust a cached value), but for
    the signature layer rather than the plain hash. Open to any
    authenticated user who can otherwise read this document (unlike
    POST /verify, which is forensic-only): confirming who signed something
    and whether it still matches isn't a privileged action, it's what makes
    a signature useful to everyone relying on the document.

    Response `result` is exactly one of:
      "no_signature" -- nothing has been signed on this document yet.
      "valid"        -- the signature matches the signer's public key AND
                        the file's hash right now (i.e. unaltered since
                        signing).
      "invalid"      -- there is a signature, but it does not match --
                        either the file changed since signing, or the
                        stored signature/key is corrupt.
    A 503 is raised (never a fabricated valid/invalid) only when the check
    itself could not be performed at all, e.g. the 'cryptography' library
    isn't installed in this deployment.
    """
    doc = get_authorised_document(db, user, document_id, Action.DOC_SIGNATURE_VERIFY, request=request)
    checked_at = datetime.now(timezone.utc)

    signature = doc.latest_signature
    if signature is None:
        log_audit(
            db,
            action=AuditAction.signature_verify,
            detail=f"Signature check on {doc.name}: no signature on file.",
            user=user,
            ip_address=get_client_ip(request),
            case_id=doc.case_id,
            document_id=doc.id,
        )
        return SignatureVerifyResult(
            document_id=doc.id,
            result="no_signature",
            checked_at=checked_at,
            detail="This document has not been digitally signed.",
        )

    file_path = settings.STORAGE_DIR / doc.file_path
    if not file_path.exists():
        raise HTTPException(410, "Evidence file is missing from storage.")
    current_hash = sha256_of_file(file_path)

    signer = signature.signer
    if signer is None or not signer.public_key_pem:
        # The signature record exists but there is no key to check it
        # against (signer account deleted, or created before signing keys
        # existed). Never report this as "invalid" -- that would claim a
        # forgery we have no basis for. Surface it as a check failure.
        raise HTTPException(
            503,
            "Cannot verify this signature: the signer's public key is not on file.",
        )

    try:
        matches = verify_signature(signer.public_key_pem, current_hash, signature.signature, signature.algorithm)
    except SigningError as exc:
        raise HTTPException(503, f"Signature verification unavailable: {exc}")

    result = "valid" if matches else "invalid"
    detail = (
        f"Signature by '{signer.username}' on {doc.name} is valid "
        f"(current file hash matches what was signed)."
        if matches else
        f"Signature by '{signer.username}' on {doc.name} does NOT match the file's current hash "
        f"-- either the file changed since signing, or the signature/key is corrupt."
    )

    log_audit(
        db,
        action=AuditAction.signature_verify,
        detail=f"Signature check on {doc.name}: {detail}",
        user=user,
        ip_address=get_client_ip(request),
        case_id=doc.case_id,
        document_id=doc.id,
    )
    return SignatureVerifyResult(
        document_id=doc.id,
        result=result,
        signer_user_id=signature.signer_user_id,
        signer_name=signature.signer_name,
        signer_role=signature.signer_role,
        algorithm=signature.algorithm,
        signed_hash=signature.signed_hash,
        hash_now=current_hash,
        signed_at=signature.created_at,
        checked_at=checked_at,
        detail=detail,
    )


def _build_watermark_lines(user: User, ip_address: str, now: datetime) -> list[str]:
    """Dynamic, per-download stamp: who viewed/downloaded this copy, from
    where, and when (UTC) -- built fresh from the current request, never
    hard-coded, so every rendered PDF is individually traceable back to a
    single access event in the audit log."""
    return [
        "CONFIDENTIAL",
        f"VIEWED BY {user.username.upper()} ({user.role_label.upper()})",
        f"IP {ip_address} | {now.strftime('%Y-%m-%d %H:%M:%S')} UTC",
    ]


@router.get("/{document_id}/download")
def download_document(
    document_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = get_authorised_document(db, user, document_id, Action.DOC_DOWNLOAD, request=request)

    file_path = settings.STORAGE_DIR / doc.file_path
    if not file_path.exists():
        raise HTTPException(410, "Evidence file is missing from storage.")

    log_audit(
        db,
        action=AuditAction.download,
        detail=f"'{user.username}' downloaded {doc.name}",
        user=user,
        ip_address=get_client_ip(request),
        case_id=doc.case_id,
        document_id=doc.id,
    )

    is_pdf = doc.type == DocType.PDF or (doc.content_type or "").lower() == "application/pdf"
    if not is_pdf:
        # Non-PDF evidence (images, audio/video, etc.) is returned as-is --
        # watermarking here only covers the PDF stream per this feature.
        return FileResponse(
            path=file_path, filename=doc.name, media_type=doc.content_type or "application/octet-stream"
        )

    ip_address = get_client_ip(request)
    now = datetime.now(timezone.utc)
    lines = _build_watermark_lines(user, ip_address, now)

    try:
        stamped = stamp_pdf_watermark(file_path, lines)
    except Exception:
        # Never let a watermarking failure silently hand out an unmarked
        # copy of a sensitive document -- fail the request instead.
        raise HTTPException(500, "Could not prepare a watermarked copy of this document.")

    return StreamingResponse(
        stamped,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{doc.name}"'},
    )
