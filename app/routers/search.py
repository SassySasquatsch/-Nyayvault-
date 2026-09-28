from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.abac import Action, filter_visible_cases
from app.database import get_db
from app.dependencies import get_client_ip, get_current_user, log_audit
from app.models import AuditAction, Case, Document, User
from app.schemas import SearchResultItem

router = APIRouter(prefix="/api/search", tags=["search"])

SNIPPET_CONTEXT_CHARS = 60  # characters of context shown either side of a match inside ocr_text


def _build_snippet(doc: Document, q: str) -> str:
    """Filename/hash match -> a plain label, same as before. A match found
    only inside the document's extracted text (see app/utils/ocr_utils.py)
    -> a short excerpt around the match instead, so the hit is actually
    useful rather than just "somewhere in this file"."""
    if q.lower() in doc.name.lower() or q.lower() in doc.hash_sha256.lower():
        return f"Evidence match: {doc.name} ({doc.type.value})"

    text = doc.ocr_text or ""
    idx = text.lower().find(q.lower())
    if idx == -1:
        return f"Evidence match: {doc.name} ({doc.type.value})"

    start = max(0, idx - SNIPPET_CONTEXT_CHARS)
    end = min(len(text), idx + len(q) + SNIPPET_CONTEXT_CHARS)
    excerpt = text[start:end].replace("\n", " ").strip()
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    method_label = "OCR" if doc.ocr_method == "ocr" else "text"
    return f"{doc.name} ({method_label} match): {prefix}{excerpt}{suffix}"


@router.get("", response_model=list[SearchResultItem])
def search(
    q: str = Query(..., min_length=1),
    request: Request = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Real (if simple) full-text-ish search: matches the query against case
    numbers/titles, evidence file names/hashes, and each document's
    extracted text -- a real PDF text layer, or Tesseract OCR output for
    scanned PDFs and images (see app/utils/ocr_utils.py, filled in by a
    background task shortly after upload). Audio content still isn't
    covered here (see /documents/{id}/transcribe for that).
    """
    like = f"%{q}%"
    results: list[SearchResultItem] = []

    # ABAC: search only ever returns cases/evidence the caller is authorised
    # for in their organisational scope. Filtering happens *before* results
    # are built, so nothing outside scope can leak via snippets or counts.
    cases = filter_visible_cases(
        user,
        db.query(Case).filter(or_(Case.number.ilike(like), Case.title.ilike(like))).all(),
        Action.SEARCH,
    )
    for c in cases:
        results.append(
            SearchResultItem(
                case_id=c.id,
                case_number=c.number,
                snippet=f"Case match: {c.title}",
            )
        )

    doc_hits = (
        db.query(Document)
        .filter(
            or_(
                Document.name.ilike(like),
                Document.hash_sha256.ilike(like),
                Document.ocr_text.ilike(like),
            )
        )
        .all()
    )
    visible_ids = {c.id for c in filter_visible_cases(user, {d.case for d in doc_hits if d.case}, Action.SEARCH)}
    docs = [d for d in doc_hits if d.case_id in visible_ids]
    for d in docs:
        results.append(
            SearchResultItem(
                case_id=d.case_id,
                case_number=d.case.number if d.case else "—",
                document_id=d.id,
                document_name=d.name,
                snippet=_build_snippet(d, q),
            )
        )

    if request is not None:
        log_audit(
            db,
            action=AuditAction.search,
            detail=f"'{user.username}' searched for \"{q}\" ({len(results)} results)",
            user=user,
            ip_address=get_client_ip(request),
        )

    return results
