from app.database import (
    Base,
    SessionLocal,
    engine,
    ensure_abac_schema,
    ensure_document_category_schema,
    ensure_signature_schema,
)
from app.models import Case, CaseStatus, User, UserRole, UserStatus
from app.security import hash_password

Base.metadata.create_all(bind=engine)
ensure_abac_schema()   # adds the ABAC columns if this is an older database
ensure_document_category_schema()   # adds documents.category if this is an older database

DEMO_PASSWORD = "NyayVault@123"  # same password for every seeded demo account

# ---------------------------------------------------------------------------
# SAMPLE organisations -- demo data only. The ABAC engine (app/abac.py) knows
# nothing about these; any state / district / unit strings work. "*" on a user
# means "every value at that level".
# ---------------------------------------------------------------------------
UK_A = dict(state="Uttarakhand", district="Dehradun", unit="Unit A")
UK_B = dict(state="Uttarakhand", district="Dehradun", unit="Unit B")
MH_B = dict(state="Maharashtra", district="Mumbai", unit="Unit B")

DEMO_USERS = [
    # --- Uttarakhand / Dehradun ---
    dict(full_name="Insp. R. Sharma", username="officer.sharma", badge_id="IO-2291",
         role=UserRole.io, status=UserStatus.approved, **UK_A),
    dict(full_name="Insp. M. Bhatt", username="officer.bhatt", badge_id="IO-2340",
         role=UserRole.io, status=UserStatus.pending, **UK_A),
    dict(full_name="Insp. S. Negi", username="officer.negi", badge_id="IO-2412",
         role=UserRole.io, status=UserStatus.approved, **UK_B),
    dict(full_name="Dr. A. Rao", username="dr.rao", badge_id="FS-1042",
         role=UserRole.forensic, status=UserStatus.approved,
         state="Uttarakhand", district="Dehradun", unit="*"),
    dict(full_name="Justice K. Verma", username="justice.verma", badge_id="JC-0087",
         role=UserRole.judge, status=UserStatus.approved,
         state="Uttarakhand", district="Dehradun", unit="*"),
    # --- Maharashtra / Mumbai ---
    dict(full_name="Insp. P. Kulkarni", username="officer.kulkarni", badge_id="IO-3105",
         role=UserRole.io, status=UserStatus.approved, **MH_B),
    dict(full_name="Dr. N. Deshmukh", username="dr.deshmukh", badge_id="FS-2210",
         role=UserRole.forensic, status=UserStatus.approved,
         state="Maharashtra", district="Mumbai", unit="*"),
    # --- system oversight: exempt from org scoping via ABAC_ORG_WIDE_ROLES ---
    dict(full_name="System Administrator", username="admin", badge_id="AD-0001",
         role=UserRole.admin, status=UserStatus.approved),
]

# (case fields, owner username, scope)
DEMO_CASES = [
    (dict(number="FIR-2026-000341", title="State vs. Rakesh Malhotra", status=CaseStatus.active), "officer.sharma", UK_A),
    (dict(number="FIR-2026-000298", title="State vs. Unknown (Cyber Fraud)", status=CaseStatus.court), "officer.sharma", UK_A),
    (dict(number="FIR-2026-000187", title="State vs. Devendra Rawat", status=CaseStatus.closed), "officer.sharma", UK_A),
    (dict(number="FIR-2026-000355", title="State vs. Priya Nair", status=CaseStatus.active), "officer.sharma", UK_A),
    # other organisations -> officer.sharma must NOT be able to reach these
    (dict(number="FIR-2026-000402", title="State vs. Vikram Bisht (Land Fraud)", status=CaseStatus.active), "officer.negi", UK_B),
    (dict(number="FIR-2026-000412", title="State vs. Anil Deshmukh (Cargo Theft)", status=CaseStatus.active), "officer.kulkarni", MH_B),
]

# Demo case numbers used to be in older formats (e.g. FIR-2026-0341). New cases
# must be FIR-YYYY-NNNNNN, so the demo data uses that format too. A database
# seeded before the change keeps its old numbers: they are recognised here so
# re-running the seed doesn't create duplicates.
LEGACY_CASE_NUMBERS = {
    "FIR-2026-000341": "FIR-2026-0341",
    "FIR-2026-000298": "FIR-2026-0298",
    "FIR-2026-000187": "FIR-2026-0187",
    "FIR-2026-000355": "FIR-2026-0355",
    "FIR-2026-000402": "FIR-2026-0402",
    "FIR-2026-000412": "FIR-MH-2026-0412",
}

SCOPE_FIELDS = ("state", "district", "unit")


def _fill_missing(obj, values):
    """Only fills attributes that are still empty -- never overwrites values an
    administrator has already set."""
    for k, v in values.items():
        if not getattr(obj, k, None):
            setattr(obj, k, v)


def run():
    db = SessionLocal()
    try:
        created_users = {}
        for u in DEMO_USERS:
            existing = db.query(User).filter(User.username == u["username"]).first()
            if existing:
                _fill_missing(existing, {k: u[k] for k in SCOPE_FIELDS if k in u})
                created_users[u["username"]] = existing
                continue
            user = User(**u, hashed_password=hash_password(DEMO_PASSWORD))
            db.add(user)
            db.flush()
            created_users[u["username"]] = user

        for fields, owner_username, scope in DEMO_CASES:
            owner = created_users[owner_username]
            existing = db.query(Case).filter(Case.number == fields["number"]).first()
            if existing is None and fields["number"] in LEGACY_CASE_NUMBERS:
                existing = db.query(Case).filter(Case.number == LEGACY_CASE_NUMBERS[fields["number"]]).first()
            if existing:
                # older database: give the demo case an owner + scope, keep everything else
                _fill_missing(existing, dict(owner_id=owner.id, **scope))
                continue
            db.add(Case(**fields, created_by_id=owner.id, owner_id=owner.id, **scope))

        db.commit()

        # Every demo account gets a signing keypair (see app/utils/signing.py)
        # so forensic-report / court-order / case-closure signing works
        # out of the box. Additive + idempotent -- never touches a user who
        # already has keys, and quietly does nothing if the 'cryptography'
        # library isn't installed.
        ensure_signature_schema()

        print("Seed complete.")
        print(f"Demo password for every account: {DEMO_PASSWORD}\n")
        print(f"  {'username':<17}{'role':<10}{'badge':<9}{'status':<10}scope (state / district / unit)")
        for u in DEMO_USERS:
            scope = " / ".join(u.get(k) or "—" for k in SCOPE_FIELDS) if u["role"] != UserRole.admin else "org-wide (oversight)"
            print(f"  {u['username']:<17}{u['role'].value:<10}{u['badge_id']:<9}{u['status'].value:<10}{scope}")
        print("\nSample cases (owner -> scope):")
        for fields, owner_username, scope in DEMO_CASES:
            print(f"  {fields['number']:<18} {owner_username:<17} {' / '.join(scope[k] for k in SCOPE_FIELDS)}")
        print("\nEvidence documents are not seeded with placeholder files -- ")
        print("upload real files through the 'io' or 'forensic' accounts to")
        print("populate a case with real, hashed evidence.")
        print("\nTo populate realistic evidence, audit history, and exercise")
        print("every feature (OCR, watermarking, redaction, transcription,")
        print("blockchain-anchor hook, verification, lifecycle, ABAC, court")
        print("presentation, reports, user approval) through the real API,")
        print("start the server in another terminal and then run:")
        print("  python scripts/populate_demo_data.py")
    finally:
        db.close()


if __name__ == "__main__":
    run()
