from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Columns added for ABAC. create_all() only creates *missing tables*, so an
# existing database (SQLite or Postgres) needs these added in place.
_ABAC_COLUMNS = {
    "users": ["state", "district", "unit"],
    "cases": ["owner_id", "state", "district", "unit"],
}


def ensure_abac_schema(bind=None):
    """Additive + idempotent: adds the ABAC columns if they are missing and
    back-fills what can be derived. Never drops, rewrites or deletes anything.

    Back-fill rules (only ever fills NULLs):
      cases.owner_id  <- cases.created_by_id
      cases.<scope>   <- the creating officer's <scope>, when that is set
    """
    bind = bind or engine
    insp = inspect(bind)
    with bind.begin() as conn:
        for table, cols in _ABAC_COLUMNS.items():
            if not insp.has_table(table):
                continue
            have = {c["name"] for c in insp.get_columns(table)}
            for col in cols:
                if col not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} VARCHAR"))
        conn.execute(text("UPDATE cases SET owner_id = created_by_id WHERE owner_id IS NULL AND created_by_id IS NOT NULL"))
        for col in ("state", "district", "unit"):
            conn.execute(text(
                f"UPDATE cases SET {col} = (SELECT u.{col} FROM users u WHERE u.id = cases.created_by_id) "
                f"WHERE {col} IS NULL AND created_by_id IS NOT NULL"
            ))


def ensure_document_category_schema(bind=None):
    """Additive + idempotent: adds documents.category (default 'evidence') to an
    existing database and, on PostgreSQL, registers the new audit action value.
    Existing rows are back-filled to 'evidence'; nothing is dropped or rewritten.
    """
    bind = bind or engine
    insp = inspect(bind)
    with bind.begin() as conn:
        if insp.has_table("documents"):
            have = {c["name"] for c in insp.get_columns("documents")}
            if "category" not in have:
                conn.execute(text("ALTER TABLE documents ADD COLUMN category VARCHAR DEFAULT 'evidence'"))
            conn.execute(text("UPDATE documents SET category = 'evidence' WHERE category IS NULL"))

    # SQLite stores enums as plain strings, so nothing to do there. A native
    # PostgreSQL enum needs the new value added explicitly (best effort: the
    # audit action is only written when a forensic report is uploaded).
    if bind.dialect.name == "postgresql" and insp.has_table("audit_logs"):
        try:
            with bind.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                conn.execute(text("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'forensic_report_upload'"))
        except Exception:  # noqa: BLE001 - never block start-up on this
            pass


def ensure_ocr_schema(bind=None):
    """Additive + idempotent: adds documents.ocr_text / ocr_method to an
    existing database and, on PostgreSQL, registers the new audit action
    value. Existing rows are left as NULL (meaning "not extracted yet") --
    nothing is dropped, rewritten, or backfilled by guessing."""
    bind = bind or engine
    insp = inspect(bind)
    with bind.begin() as conn:
        if insp.has_table("documents"):
            have = {c["name"] for c in insp.get_columns("documents")}
            if "ocr_text" not in have:
                conn.execute(text("ALTER TABLE documents ADD COLUMN ocr_text TEXT"))
            if "ocr_method" not in have:
                conn.execute(text("ALTER TABLE documents ADD COLUMN ocr_method VARCHAR"))

    if bind.dialect.name == "postgresql" and insp.has_table("audit_logs"):
        try:
            with bind.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                conn.execute(text("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'ocr_extract'"))
        except Exception:  # noqa: BLE001 - never block start-up on this
            pass


def ensure_signature_schema(bind=None):
    """Additive + idempotent: adds users.public_key_pem /
    private_key_encrypted_pem to an existing database (the 'signatures'
    table itself is new, so Base.metadata.create_all() already creates it --
    see app/main.py), registers the new AuditAction values on PostgreSQL,
    and best-effort back-fills a signing keypair for any user who doesn't
    have one yet (an existing account created before this feature, or
    created while the 'cryptography' library was unavailable). Never drops,
    rewrites, or replaces a keypair that already exists.
    """
    bind = bind or engine
    insp = inspect(bind)
    with bind.begin() as conn:
        if insp.has_table("users"):
            have = {c["name"] for c in insp.get_columns("users")}
            if "public_key_pem" not in have:
                conn.execute(text("ALTER TABLE users ADD COLUMN public_key_pem TEXT"))
            if "private_key_encrypted_pem" not in have:
                conn.execute(text("ALTER TABLE users ADD COLUMN private_key_encrypted_pem TEXT"))

    if bind.dialect.name == "postgresql" and insp.has_table("audit_logs"):
        for value in ("court_order_upload", "case_close", "sign", "signature_verify"):
            try:
                with bind.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                    conn.execute(text(f"ALTER TYPE auditaction ADD VALUE IF NOT EXISTS '{value}'"))
            except Exception:  # noqa: BLE001 - never block start-up on this
                pass

    # Best-effort keypair back-fill. Signing is an additive feature -- if the
    # 'cryptography' library isn't installed, this quietly does nothing and
    # every signing call site elsewhere continues to degrade gracefully.
    try:
        from app.utils.signing import generate_keypair, SigningError
    except Exception:  # noqa: BLE001
        return
    if not insp.has_table("users"):
        return
    with bind.begin() as conn:
        rows = conn.execute(text(
            "SELECT id FROM users WHERE public_key_pem IS NULL OR private_key_encrypted_pem IS NULL"
        )).fetchall()
        for (user_id,) in rows:
            try:
                kp = generate_keypair()
            except SigningError:
                break  # library unavailable -- no point retrying per-row
            conn.execute(
                text(
                    "UPDATE users SET public_key_pem = :pub, private_key_encrypted_pem = :priv WHERE id = :id"
                ),
                {"pub": kp.public_key_pem, "priv": kp.private_key_encrypted_pem, "id": user_id},
            )
