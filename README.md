# NyayVault

NyayVault is a FastAPI + static HTML/CSS/JavaScript digital evidence management demo. The frontend and backend are connected and served by one FastAPI process.

## Run

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python seed_data.py
uvicorn app.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000/`.


## Demo accounts

Password for all approved demo accounts: `NyayVault@123`

- `officer.sharma` — role `io`
- `dr.rao` — role `forensic`
- `justice.verma` — role `judge`
- `admin` — role `admin`
- `officer.bhatt` — role `io`, pending approval (intentionally cannot log in until approved)

The login page uses the real `/api/auth/login` endpoint and JWT authentication. Dashboard cases/documents are loaded from the database, evidence upload uses the backend upload endpoint and real SHA-256 hashing, forensic verification calls the real integrity endpoint, search calls the API, and admin user approval/revocation uses backend RBAC endpoints.

API documentation is available at `/docs` while the app is running.


## Case Document Lifecycle (read-only)

Every case has a chronological **Case Lifecycle** timeline (upload → access → verification → new version → sharing → court, …) shown as the **Lifecycle** tab of every case (IO / forensic / judge), and as the **Lifecycle** menu item for admins. Clicking an event shows who/when/what, the document name + ID, version, SHA-256 and integrity status.

- **API:** `GET /api/cases/{case_id}/lifecycle[?document_id=…]` — the only lifecycle route; no write methods exist.
- **No new tables.** It is assembled from `audit_logs` + `documents` + `users`, and reuses the existing `require_roles` RBAC.
- **What each role sees:** judge / IO — every recorded event for the case; forensic — document-linked events only (including forensic report uploads); admin — everything plus IP addresses. Nobody, admin included, can edit or delete history: there is no such route, and `app/utils/audit_guard.py` makes the ORM refuse UPDATE/DELETE on `audit_logs`.
- **Versions are inferred:** NyayVault has no version registry, so files with the same name in a case are numbered v1, v2… by upload order (the UI labels this as inferred).
- **Not recorded today:** a *reason for change* (shown as "Not recorded") — the app has no modify/replace flow to capture one.


## ABAC + organisational segregation

On top of the existing RBAC (`require_roles`, unchanged) every case, document, evidence, search, lifecycle, audit-log, report and courtroom request now also passes an attribute check (`app/abac.py`, enforced in the backend):

1. **Role** permits the action — the existing RBAC dependency.
2. **Scope** — the user's `state` / `district` / `unit` match the case's (`*` on a user = every value at that level; a missing value denies).
3. **Assigned** — for roles in `ABAC_ASSIGNMENT_ROLES` (default `io`) the user must also be the case owner.

Documents and evidence inherit the scope of their case. Lists and search are filtered to what the caller may see; direct access to anything else returns `403` and writes an `access_denied` audit event. Audit/lifecycle history has no write route for any role, and `app/utils/audit_guard.py` still refuses UPDATE/DELETE.

Nothing names a state: sample orgs (Uttarakhand/Dehradun Unit A & B, Maharashtra/Mumbai Unit B) exist only in `seed_data.py`. Configure via env vars — see `.env.example` (`ABAC_SCOPE_ATTRIBUTES`, `ABAC_ORG_WIDE_ROLES`, `ABAC_ASSIGNMENT_ROLES`, `ABAC_ROLE_DOC_TYPES`). New users can get attributes via `POST /api/users` (`state`, `district`, `unit`).

**Upgrading an existing database:** restart (columns are added in place), then run `python seed_data.py` once to fill sample scopes/owners (it only fills empty values).

## MVP navigation

| Role | Menu | Inside a case |
|------|------|---------------|
| IO | Overview (My Cases + **+ Add Case**), Search | Overview · Documents · Evidence · Lifecycle |
| Forensic | Overview, Cases | Overview · Evidence · Verify · Forensic Report · Lifecycle — with **+ Upload Forensic Report** |
| Judge | Overview, Search | Overview · Documents · Evidence · Lifecycle — with the **Court Presentation** action |
| Admin | Overview, Users, Audit Logs, Lifecycle | — |

- **Document Details** (the *Details* button on any file) shows the SHA-256, uploader, time, integrity status, blockchain tx and the EXIF / metadata that used to have its own menu item, plus an authenticated **Download**.
- Redaction, Audio/Transcription, the standalone Report generator and the EXIF inspector are **hidden from the menu, not removed**: `POST /api/documents/{id}/redact/*`, `POST /api/documents/{id}/transcribe` and `GET /api/cases/{id}/report` still work with their RBAC + ABAC checks, and adding an id back to `NAV_CONFIG` in `frontend/js/dashboard.js` restores the screen.
- Case files are sorted by type: video / audio / images are **Evidence**; PDFs, Word files, forensic reports and everything else are **Documents**. A forensic officer has no Documents tab, so their Evidence tab lists every file except forensic reports.

## FIR number format

New cases must use `FIR-YYYY-NNNNNN` (e.g. `FIR-2026-445566`): the letters `FIR`, a four-digit year, a six-digit number. `ABC123`, `N1`, `FIR-2026-0341`, lowercase, extra text etc. are rejected with `422` by `POST /api/cases` and by the Add Case form. Only *new* cases are checked — cases already in a database keep their old numbers and keep working. The demo seed data now uses the new format (`FIR-2026-000341` …); re-running `seed_data.py` on an older database recognises the old demo numbers and does not duplicate them.

## Forensic reports

`POST /api/cases/{case_id}/forensic-reports` (multipart `file`, `.pdf` / `.doc` / `.docx`) — **forensic role only**, and the case must be inside the officer's ABAC scope.

- The server computes the **SHA-256**, and stores the **uploader** and **timestamp** on the document (`documents.category = 'forensic_report'`).
- It writes a `forensic_report_upload` audit event (hash in the detail), which is what places it on the case **lifecycle** and audit trail, and anchors the hash on the blockchain in the background when anchoring is enabled.
- Access afterwards is the normal document access: `GET /api/documents/{id}`, `/download`, `/verify` and `GET /api/cases/{id}/forensic-reports` pass RBAC + ABAC (scope, and ownership for an IO); anyone else gets `403` (audited as `access_denied`) or `401`.
- The generic evidence upload cannot create a forensic report — `category` is never read from the request.
- Existing databases are upgraded in place on start-up (`documents.category`, back-filled to `evidence`).

**IO dashboard:** *My Cases* + **+ Add Case** (uses `POST /api/cases`; creator becomes owner and the case takes their scope), case cards, *Recent Activity*, and per-case tabs Overview | Documents | Evidence | Lifecycle (see *MVP navigation* above). Video/audio/image files show under Evidence; everything else under Documents.

Tests: `pip install httpx && python -m unittest discover -s tests -v`

## Populating realistic demo data

`seed_data.py` only creates users and cases -- it deliberately leaves cases
without evidence, since files need to be hashed for real. To exercise every
feature end-to-end (real SHA-256 evidence with EXIF, OCR-searchable text,
PDF PII redaction, CCTV redaction, audio transcription, watermarked
downloads, forensic report upload + verification, case lifecycle, ABAC scope
denial, court presentation, case report generation, user approval, and the
audit trail) through the real API rather than by writing rows directly into
the database:

```bash
pip install -r requirements-dev.txt   # adds httpx, used to call the API
python seed_data.py
uvicorn app.main:app --reload --port 8000   # keep running in one terminal
python scripts/populate_demo_data.py        # run in a second terminal
```

The script generates its own sample files (a witness-statement PDF with
sample Indian PII, a JPEG with EXIF/GPS, a short WAV clip, a forensic-report
PDF, and a stand-in CCTV file) under `scripts/demo_fixtures/` and then logs
in as each demo account to drive the real endpoints. It's idempotent enough
to re-run, though re-running will create additional documents/audit entries
rather than replacing the previous run's.
