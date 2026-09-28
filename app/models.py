import enum
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.database import Base


def gen_id(prefix: str) -> str:
    """Short, readable, collision-safe ids e.g. usr_3f9a2b1c."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Enums -- mirrored 1:1 with the values the frontend already hardcodes in
# js/data.js and js/dashboard.js (NAV_CONFIG, ROLE_META, status badges...).
# ---------------------------------------------------------------------------
class UserRole(str, enum.Enum):
    io = "io"                # Investigating Officer
    forensic = "forensic"    # Forensic Specialist
    judge = "judge"          # Judge / Court
    admin = "admin"          # Administrator


class UserStatus(str, enum.Enum):
    approved = "approved"
    pending = "pending"


class CaseStatus(str, enum.Enum):
    active = "active"
    court = "court"
    closed = "closed"


class DocType(str, enum.Enum):
    VIDEO = "VIDEO"
    PDF = "PDF"
    AUDIO = "AUDIO"
    IMAGE = "IMAGE"
    OTHER = "OTHER"


class DocStatus(str, enum.Enum):
    pending = "pending"      # uploaded, not yet hash-verified
    verified = "verified"
    tampered = "tampered"


class SignaturePurpose(str, enum.Enum):
    """Why a hash was signed -- the three actions the task calls out as
    needing legal weight. Kept as its own enum (rather than reusing
    AuditAction) because a Signature and an AuditLog entry answer different
    questions: the audit log says *that* something legally significant
    happened; the Signature is the cryptographic proof of *who*."""
    forensic_report = "forensic_report"   # forensic officer signs their own report's hash
    court_order = "court_order"           # judge signs an uploaded court order/judgment's hash
    case_closure = "case_closure"         # judge signs a canonical case-closure statement


class AuditAction(str, enum.Enum):
    login = "login"
    login_failed = "login_failed"
    logout = "logout"
    upload = "upload"
    view = "view"
    verify = "verify"
    tamper = "tamper"
    download = "download"
    present = "present"
    approve = "approve"
    revoke = "revoke"
    redact = "redact"
    transcribe = "transcribe"
    report = "report"
    search = "search"
    case_create = "case_create"
    access_denied = "access_denied"   # ABAC refusal (see app/abac.py)
    user_create = "user_create"
    blockchain_anchor = "blockchain_anchor"
    blockchain_anchor_failed = "blockchain_anchor_failed"
    forensic_report_upload = "forensic_report_upload"   # forensic officer uploads an examination report
    ocr_extract = "ocr_extract"   # background text extraction (text layer or Tesseract OCR) for search
    court_order_upload = "court_order_upload"   # judge uploads a court order / judgment
    case_close = "case_close"     # judge closes a case
    sign = "sign"                 # a document's hash (or a case-closure statement) was digitally signed
    signature_verify = "signature_verify"   # a stored signature was re-verified


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: gen_id("usr"))
    full_name = Column(String, nullable=False)
    username = Column(String, unique=True, nullable=False, index=True)
    badge_id = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    status = Column(Enum(UserStatus), nullable=False, default=UserStatus.pending)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # ABAC organisational attributes (free-form text, so any state / agency /
    # unit can be represented). "*" = every value at that level; NULL = none,
    # which denies access. See app/abac.py.
    state = Column(String, nullable=True)
    district = Column(String, nullable=True)
    unit = Column(String, nullable=True)

    # Per-user signing keypair (see app/utils/signing.py), generated once at
    # account creation (app/routers/users.py create_user). public_key_pem is
    # plaintext by design -- verifying a signature never needs the private
    # key. private_key_encrypted_pem is PKCS#8 PEM, encrypted with a key
    # derived from the server's SECRET_KEY, never used directly by anything
    # other than app/utils/signing.py. Both are nullable: a user created
    # before this feature existed, or created while the 'cryptography'
    # library was unavailable, simply has no keys and can't sign -- every
    # signing call site degrades gracefully rather than requiring them.
    public_key_pem = Column(Text, nullable=True)
    private_key_encrypted_pem = Column(Text, nullable=True)

    documents = relationship("Document", back_populates="uploader")
    audit_logs = relationship("AuditLog", back_populates="user")

    @property
    def role_label(self) -> str:
        return {
            "io": "Investigating Officer",
            "forensic": "Forensic Specialist",
            "judge": "Judge / Court",
            "admin": "Administrator",
        }[self.role.value if isinstance(self.role, UserRole) else self.role]


class Case(Base):
    __tablename__ = "cases"

    id = Column(String, primary_key=True, default=lambda: gen_id("case"))
    number = Column(String, unique=True, nullable=False, index=True)  # FIR-2026-445566 (FIR-YYYY-NNNNNN)
    title = Column(String, nullable=False)
    status = Column(Enum(CaseStatus), nullable=False, default=CaseStatus.active)
    created_by_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # ABAC resource attributes. owner_id is the assigned IO; the organisational
    # scope is stamped from the creating officer when the case is opened.
    owner_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    state = Column(String, nullable=True)
    district = Column(String, nullable=True)
    unit = Column(String, nullable=True)

    owner = relationship("User", foreign_keys=[owner_id])
    documents = relationship(
        "Document", back_populates="case", cascade="all, delete-orphan"
    )

    @property
    def owner_name(self):
        return self.owner.full_name if self.owner else None

    @property
    def doc_count(self) -> int:
        return len(self.documents)


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=lambda: gen_id("doc"))
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    name = Column(String, nullable=False)
    type = Column(Enum(DocType), nullable=False)
    file_path = Column(String, nullable=False)   # path on disk, relative to STORAGE_DIR
    size_bytes = Column(Integer, default=0)
    content_type = Column(String, nullable=True)

    uploader_id = Column(String, ForeignKey("users.id"), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    hash_sha256 = Column(String, nullable=False)   # hash computed at upload time
    status = Column(Enum(DocStatus), nullable=False, default=DocStatus.pending)
    last_verified_at = Column(DateTime(timezone=True), nullable=True)

    # Optional: set once a background task successfully anchors hash_sha256
    # on-chain (see app/utils/blockchain_anchor.py). NULL until then, and
    # stays NULL forever if blockchain anchoring is disabled/unconfigured --
    # this is purely an added proof layer, never a dependency for normal
    # reads/writes of the document record.
    blockchain_tx_hash = Column(String, nullable=True)

    # "evidence" (default, everything uploaded through POST /api/cases/{id}/documents)
    # or "forensic_report" (only created by a forensic officer through
    # POST /api/cases/{id}/forensic-reports). See app/utils/doc_category.py.
    category = Column(String, nullable=False, default="evidence", server_default="evidence")

    # Metadata extracted at upload time (EXIF for images, best-effort for
    # everything else). Stored as JSON: {device, gps, imei, created}
    exif = Column(JSON, default=dict)

    # Full-text content used to make this document searchable via
    # /api/search, filled in by a background task shortly after upload (see
    # app/utils/ocr_utils.py). NULL until that task runs, and stays NULL if
    # nothing could be extracted (unsupported type, or no OCR engine
    # available on this host) -- same "never blocks, never fails the
    # upload" pattern as blockchain_tx_hash above. Never derived from, or
    # written back to, the evidence file itself.
    ocr_text = Column(Text, nullable=True)
    # How ocr_text was obtained: "text_layer" (real embedded PDF text, no
    # OCR needed) or "ocr" (Tesseract). NULL until the background task runs.
    ocr_method = Column(String, nullable=True)

    case = relationship("Case", back_populates="documents")
    uploader = relationship("User", back_populates="documents")
    signatures = relationship(
        "Signature",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="Signature.created_at",
    )

    @property
    def latest_signature(self):
        """Most recent signature on this document, or None. A document can
        in principle be signed more than once (e.g. re-signed after a
        correction), but every current signer_purpose only signs once per
        upload, so in practice this is the signature."""
        return self.signatures[-1] if self.signatures else None

    @property
    def uploader_name(self):
        return self.uploader.full_name if self.uploader else None

    @property
    def hash_display(self) -> str:
        """Shortened hash for list views, matching the frontend's
        '9f2a1c...4e0b7d' style."""
        h = self.hash_sha256
        return f"{h[:6]}...{h[-6:]}" if len(h) > 14 else h

    @property
    def blockchain_explorer_url(self):
        """Clickable block-explorer link for blockchain_tx_hash (e.g. a
        Polygonscan Amoy URL), or None if this document isn't anchored yet
        or no explorer is configured for the current chain. Computed on
        read from live settings (app/utils/blockchain_anchor.py) rather than
        stored, so it always reflects the chain currently configured --
        it never goes stale if BLOCKCHAIN_CHAIN_ID changes later."""
        from app.utils.blockchain_anchor import get_explorer_tx_url

        return get_explorer_tx_url(self.blockchain_tx_hash)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=lambda: gen_id("log"))
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    role = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    action = Column(Enum(AuditAction), nullable=False)
    detail = Column(Text, nullable=False, default="")
    case_id = Column(String, ForeignKey("cases.id"), nullable=True)
    document_id = Column(String, ForeignKey("documents.id"), nullable=True)

    user = relationship("User", back_populates="audit_logs")


class Signature(Base):
    """
    A non-repudiable digital signature over a hash that already exists
    elsewhere -- never a hash this table computes itself. Two shapes:

      - document_id set, case_id NULL: signs Document.hash_sha256 (a
        forensic report or an uploaded court order/judgment). See
        app/routers/documents.py.
      - case_id set, document_id NULL: signs a canonical, deterministic
        description of a case-closure event (there is no file to hash),
        produced by app/utils/hashing.sha256_of_bytes. See
        app/routers/cases.py close_case.

    Exactly one of document_id / case_id is set on any row; nothing in the
    schema enforces that (SQLite has no CHECK-constraint story worth
    relying on here), so every writer is responsible for setting exactly
    one -- mirrored in app/routers/documents.py and app/routers/cases.py.
    """
    __tablename__ = "signatures"

    id = Column(String, primary_key=True, default=lambda: gen_id("sig"))
    document_id = Column(String, ForeignKey("documents.id"), nullable=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=True, index=True)
    signer_user_id = Column(String, ForeignKey("users.id"), nullable=False)
    purpose = Column(Enum(SignaturePurpose), nullable=False)

    # The exact hash that was signed -- for a document this is always
    # Document.hash_sha256 as it stood at signing time (copied here, not
    # just referenced, so the signature remains checkable even if the
    # document row is later altered); for a case closure it's the
    # closure-statement hash described above.
    signed_hash = Column(String, nullable=False)
    signature = Column(Text, nullable=False)     # base64-encoded signature bytes
    algorithm = Column(String, nullable=False)   # e.g. "RSA-PSS-SHA256" -- see app/utils/signing.py
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    document = relationship("Document", back_populates="signatures")
    case = relationship("Case")
    signer = relationship("User")

    @property
    def signer_name(self):
        return self.signer.full_name if self.signer else None

    @property
    def signer_role(self):
        if not self.signer:
            return None
        return self.signer.role.value if isinstance(self.signer.role, UserRole) else self.signer.role
