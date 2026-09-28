from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.abac import Action, get_authorised_document
from app.config import settings
from app.database import get_db
from app.dependencies import get_client_ip, log_audit, require_roles
from app.models import AuditAction, Document, User
from app.schemas import TranscriptionResult, TranscriptLine

router = APIRouter(prefix="/api/documents", tags=["audio"])

_SIMULATED_LINES = [
    ("00:02", "[simulated] Speaker 1: reached the location."),
    ("00:07", "[simulated] Speaker 2: noted, what colour was the vehicle?"),
    ("00:11", "[simulated] Speaker 1: red, plate not clearly visible."),
    ("00:18", "[simulated] Speaker 2: understood, forwarding now."),
]


@router.post("/{document_id}/transcribe", response_model=TranscriptionResult)
def transcribe_document(
    document_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("io", "forensic")),
):
    doc = get_authorised_document(db, user, document_id, Action.DOC_TRANSCRIBE, request=request)
    if doc.type.value != "AUDIO":
        raise HTTPException(400, "This document is not an audio file.")

    file_path = settings.STORAGE_DIR / doc.file_path
    simulated = True
    lines: list[TranscriptLine] = []

    try:
        import speech_recognition as sr

        recognizer = sr.Recognizer()
        with sr.AudioFile(str(file_path)) as source:
            audio = recognizer.record(source)
        text = recognizer.recognize_sphinx(audio)  # offline engine, needs pocketsphinx
        simulated = False
        lines = [TranscriptLine(timestamp="00:00", text=text)]
    except ImportError:
        lines = [TranscriptLine(timestamp=ts, text=text) for ts, text in _SIMULATED_LINES]
    except Exception:
        # Wrong audio codec/sample rate, pocketsphinx not installed, silence,
        # etc. -- fall back to the labeled simulated transcript rather than
        # a 500 error, since this is a best-effort feature.
        lines = [TranscriptLine(timestamp=ts, text=text) for ts, text in _SIMULATED_LINES]

    log_audit(
        db,
        action=AuditAction.transcribe,
        detail=f"'{user.username}' transcribed {doc.name} ({'simulated' if simulated else 'real'})",
        user=user,
        ip_address=get_client_ip(request),
        case_id=doc.case_id,
        document_id=doc.id,
    )
    return TranscriptionResult(document_id=doc.id, lines=lines, simulated=simulated)
