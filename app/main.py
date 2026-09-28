from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.database import (
    Base,
    engine,
    ensure_abac_schema,
    ensure_document_category_schema,
    ensure_ocr_schema,
    ensure_signature_schema,
)
from app.routers import audio, audit_logs, auth, cases, documents, lifecycle, redaction, reports, search, users
from app.utils import audit_guard  # noqa: F401  (registers the append-only guard on audit_logs)

# Create tables if they don't exist yet. For anything beyond local/demo use,
# swap this for a real migration tool (Alembic) instead.
Base.metadata.create_all(bind=engine)
ensure_abac_schema()  # additive: adds the ABAC columns to an existing database
ensure_document_category_schema()  # additive: documents.category (evidence / forensic_report)
ensure_ocr_schema()  # additive: documents.ocr_text / ocr_method (scanned-PDF & image OCR)
ensure_signature_schema()  # additive: users signing keypairs + signatures table/back-fill

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Backend for NyayVault — Digital Evidence Management System. "
        "Handles auth/RBAC, case & evidence records, SHA-256 chain-of-custody "
        "hashing and integrity verification, audit logging, search, PDF "
        "report generation, and best-effort redaction/transcription."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(cases.router)
app.include_router(documents.router)
app.include_router(documents.cases_router)
app.include_router(reports.router)
app.include_router(redaction.router)
app.include_router(audio.router)
app.include_router(search.router)
app.include_router(audit_logs.router)
app.include_router(lifecycle.router)

# NOTE: uploaded evidence and generated reports are deliberately NOT mounted as
# public static files any more. A static mount would bypass authentication,
# ABAC and the audit log. Files are served only through
# GET /api/documents/{id}/download and GET /api/cases/{id}/report.


@app.get("/api/health", tags=["health"])
def health_check():
    return {"status": "ok", "service": settings.APP_NAME, "version": settings.APP_VERSION}


# Serve the frontend from the same FastAPI process so the UI and API are
# connected with no separate web server or CORS setup required.
FRONTEND_DIR = settings.BASE_DIR / "frontend" if hasattr(settings, "BASE_DIR") else None
from pathlib import Path as _Path
FRONTEND_DIR = _Path(__file__).resolve().parent.parent / "frontend"

@app.get("/", include_in_schema=False)
def frontend_login():
    return FileResponse(FRONTEND_DIR / "login.html")

app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
