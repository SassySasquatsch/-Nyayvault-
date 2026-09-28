from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import AuditAction, CaseStatus, DocStatus, DocType, SignaturePurpose, UserRole, UserStatus
from app.utils.doc_category import DOC_CATEGORY_EVIDENCE, FIR_NUMBER_MESSAGE, is_valid_fir_number


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str
    role: UserRole


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    full_name: str
    username: str
    badge_id: str
    role: UserRole
    status: UserStatus
    created_at: datetime
    # ABAC organisational attributes ("*" = all, null = none)
    state: Optional[str] = None
    district: Optional[str] = None
    unit: Optional[str] = None


class UserCreate(BaseModel):
    full_name: str
    username: str
    badge_id: str
    role: UserRole
    state: Optional[str] = None
    district: Optional[str] = None
    unit: Optional[str] = None
    password: Optional[str] = Field(
        default=None,
        description="If omitted, a temporary password is generated and returned once.",
    )


class UserCreatedOut(BaseModel):
    user: UserOut
    temporary_password: Optional[str] = None


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------
class CaseCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    number: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    status: CaseStatus = CaseStatus.active

    @field_validator("number")
    @classmethod
    def _fir_format(cls, value: str) -> str:
        # Only FIR-YYYY-NNNNNN (e.g. FIR-2026-445566). Applies to new cases;
        # cases already in the database are never re-validated.
        if not is_valid_fir_number(value):
            raise ValueError(FIR_NUMBER_MESSAGE)
        return value


class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    number: str
    title: str
    status: CaseStatus
    created_at: datetime
    doc_count: int
    # ABAC resource attributes + owning IO
    owner_id: Optional[str] = None
    owner_name: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    unit: Optional[str] = None
    # Latest audit event on the case (denied-access attempts excluded).
    last_activity: Optional[datetime] = None


class CaseDetailOut(CaseOut):
    documents: list["DocumentOut"] = []


# ---------------------------------------------------------------------------
# Documents / Evidence
# ---------------------------------------------------------------------------
class ExifOut(BaseModel):
    device: str = "—"
    gps: str = "—"
    imei: str = "—"
    created: str = "—"


class SignatureOut(BaseModel):
    """The stored signature record itself -- returned on a document so the
    UI can show "signed by X on Y" without a second round trip, and reused
    verbatim as the "existing signature" half of SignatureVerifyResult
    further below. Never includes the raw signature bytes in a form meant
    for re-signing -- this is a read model."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: Optional[str] = None
    case_id: Optional[str] = None
    signer_user_id: str
    signer_name: Optional[str] = None
    signer_role: Optional[str] = None
    purpose: SignaturePurpose
    signed_hash: str
    algorithm: str
    created_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    name: str
    type: DocType
    size_bytes: int
    uploader_id: Optional[str]
    uploaded_at: datetime
    hash_sha256: str
    hash_display: str
    status: DocStatus
    last_verified_at: Optional[datetime]
    exif: ExifOut
    # "evidence" | "forensic_report"
    category: str = DOC_CATEGORY_EVIDENCE
    uploader_name: Optional[str] = None
    blockchain_tx_hash: Optional[str] = None
    # How ocr_text (below) was obtained -- "text_layer" | "ocr" | None if the
    # background extraction task (app/utils/ocr_utils.py) hasn't finished, or
    # nothing usable could be pulled from the file (see Document.ocr_method).
    ocr_method: Optional[str] = None
    # Full extracted text, used so /api/search can match inside scanned
    # evidence. Included here as well so a document's own detail view can
    # show what became searchable; NULL until the background task completes.
    ocr_text: Optional[str] = None
    # Derived (see Document.blockchain_explorer_url) -- a clickable
    # block-explorer link for blockchain_tx_hash, or None if not anchored
    # yet / no explorer is configured for the current chain.
    blockchain_explorer_url: Optional[str] = None
    # The document's own non-repudiable signature (see Signature model /
    # app/utils/signing.py), if one was produced at upload time -- None for
    # ordinary evidence, or for a forensic report / court order uploaded
    # while signing was unavailable (missing 'cryptography' library, or the
    # uploader has no keypair yet). Field name matches Document.latest_signature
    # so it populates automatically from the ORM object.
    latest_signature: Optional[SignatureOut] = None

    @field_validator("category", mode="before")
    @classmethod
    def _default_category(cls, value):
        return value or DOC_CATEGORY_EVIDENCE


class VerifyResult(BaseModel):
    document_id: str
    status: DocStatus
    hash_at_upload: str
    hash_now: str
    match: bool
    checked_at: datetime


# ---------------------------------------------------------------------------
# Digital signatures (non-repudiation for legally significant actions)
# ---------------------------------------------------------------------------
class SignatureVerifyResult(BaseModel):
    """Mirrors VerifyResult's shape: a flat, self-contained record of what
    was checked and when. `result` is exactly one of three values -- never
    a fabricated fourth state -- see app/utils/signing.py and
    GET /api/documents/{id}/signature/verify."""
    document_id: str
    result: Literal["valid", "invalid", "no_signature"]
    signer_user_id: Optional[str] = None
    signer_name: Optional[str] = None
    signer_role: Optional[str] = None
    algorithm: Optional[str] = None
    signed_hash: Optional[str] = None
    hash_now: Optional[str] = None
    signed_at: Optional[datetime] = None
    checked_at: datetime
    detail: str


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    timestamp: datetime
    user_id: Optional[str]
    role: Optional[str]
    ip_address: Optional[str]
    action: AuditAction
    detail: str
    case_id: Optional[str]
    document_id: Optional[str]


# ---------------------------------------------------------------------------
# Misc feature endpoints (redaction / transcription / search / overview)
# ---------------------------------------------------------------------------
class RedactionResult(BaseModel):
    document_id: str
    kind: str  # "pdf" | "cctv"
    summary: list[str]
    simulated: bool


class TranscriptLine(BaseModel):
    timestamp: str
    text: str


class TranscriptionResult(BaseModel):
    document_id: str
    lines: list[TranscriptLine]
    simulated: bool


class SearchResultItem(BaseModel):
    case_id: str
    case_number: str
    document_id: Optional[str] = None
    document_name: Optional[str] = None
    snippet: str


class OverviewOut(BaseModel):
    active_cases: int
    pending_verification: int
    evidence_items: int
    audit_events: int


class PresentSessionOut(BaseModel):
    case_id: str
    watermark_text: str
    presented_by: str
    presented_at: datetime


class CaseCloseResult(BaseModel):
    """Response for POST /api/cases/{id}/close. Wraps the updated case
    alongside the signature produced over the closure statement (None only
    if signing itself was unavailable -- see app/utils/signing.py -- the
    case is still closed either way, exactly like a document upload is
    never blocked by a failed blockchain anchor)."""
    case: CaseOut
    signature: Optional[SignatureOut] = None


# Forward refs used above (TokenResponse.user, CaseDetailOut.documents) are
# defined later in this module -- rebuild once everything exists so FastAPI
# never hits an unresolved ForwardRef at request time.
TokenResponse.model_rebuild()
CaseDetailOut.model_rebuild()

