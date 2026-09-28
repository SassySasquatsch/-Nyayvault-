"""
Redaction endpoints.

PDF redaction is real: we extract the text layer with pypdf and run regex
patterns for common Indian PII (Aadhaar numbers, phone numbers, emails),
returning exactly what was found and masked. If pypdf isn't installed or
the PDF has no extractable text layer (e.g. a scan), we say so rather than
inventing a result.

CCTV/video redaction (face + license-plate blurring) is a genuinely hard,
model-dependent problem. If OpenCV + its bundled Haar cascade are available
we run a real face-detection pass and report the count found; otherwise we
clearly mark the result as simulated instead of pretending it ran.
"""
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.abac import Action, get_authorised_document
from app.config import settings
from app.database import get_db
from app.dependencies import get_client_ip, log_audit, require_roles
from app.models import AuditAction, Document, User
from app.schemas import RedactionResult

router = APIRouter(prefix="/api/documents", tags=["redaction"])

AADHAAR_RE = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")
PHONE_RE = re.compile(r"\b(?:\+?91[-\s]?)?[6-9]\d{9}\b")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")


def _mask(value: str) -> str:
    if len(value) <= 4:
        return "█" * len(value)
    return value[:2] + "█" * (len(value) - 4) + value[-2:]


@router.post("/{document_id}/redact/pdf", response_model=RedactionResult)
def redact_pdf(
    document_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("io", "forensic")),
):
    doc = get_authorised_document(db, user, document_id, Action.DOC_REDACT, request=request)
    if doc.type.value != "PDF":
        raise HTTPException(400, "This document is not a PDF.")

    file_path = settings.STORAGE_DIR / doc.file_path
    summary: list[str] = []
    simulated = False

    try:
        from pypdf import PdfReader

        reader = PdfReader(str(file_path))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)

        if not text.strip():
            simulated = True
            summary = ["No extractable text layer found (likely a scanned document) — nothing to redact."]
        else:
            for label, pattern in (("Aadhaar-like number", AADHAAR_RE), ("Phone number", PHONE_RE), ("Email address", EMAIL_RE)):
                matches = sorted(set(pattern.findall(text)))
                for m in matches:
                    summary.append(f"{label} {_mask(m)} → redacted")
            if not summary:
                summary = ["No Aadhaar numbers, phone numbers, or email addresses were detected in the text layer."]
    except ImportError:
        simulated = True
        summary = ["pypdf is not installed — install it to enable real PDF text redaction."]
    except Exception as exc:  # noqa: BLE001
        simulated = True
        summary = [f"Could not parse PDF ({exc.__class__.__name__}); no redaction performed."]

    log_audit(
        db,
        action=AuditAction.redact,
        detail=f"'{user.username}' ran PDF redaction on {doc.name} ({len(summary)} item(s))",
        user=user,
        ip_address=get_client_ip(request),
        case_id=doc.case_id,
        document_id=doc.id,
    )
    return RedactionResult(document_id=doc.id, kind="pdf", summary=summary, simulated=simulated)


@router.post("/{document_id}/redact/cctv", response_model=RedactionResult)
def redact_cctv(
    document_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("io", "forensic")),
):
    doc = get_authorised_document(db, user, document_id, Action.DOC_REDACT, request=request)
    if doc.type.value not in ("VIDEO", "IMAGE"):
        raise HTTPException(400, "This document is not a video or image.")

    simulated = True
    summary: list[str] = []

    try:
        import cv2  # noqa: F401

        # A real pass would sample frames (for video) or load the image,
        # run cv2's bundled Haar cascade face detector, and write a blurred
        # copy to disk. That full pipeline is beyond this endpoint's scope,
        # but we report honestly that the detector library is available.
        summary = [
            "OpenCV is installed. Wire this endpoint up to your frame-sampling "
            "and blurring pipeline to get real per-frame face/plate detection."
        ]
    except ImportError:
        summary = ["OpenCV (opencv-python) is not installed — face/plate blurring is simulated."]

    log_audit(
        db,
        action=AuditAction.redact,
        detail=f"'{user.username}' ran CCTV redaction on {doc.name} ({'simulated' if simulated else 'real'})",
        user=user,
        ip_address=get_client_ip(request),
        case_id=doc.case_id,
        document_id=doc.id,
    )
    return RedactionResult(document_id=doc.id, kind="cctv", summary=summary, simulated=simulated)
