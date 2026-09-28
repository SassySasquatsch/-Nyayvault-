"""
Populate NyayVault with realistic demo data that exercises every feature
end-to-end, through the real HTTP API (not by poking the database directly).

Unlike seed_data.py -- which only creates users/cases and deliberately skips
evidence files -- this script:

  1. Generates real sample files on disk (PDF witness statement with Indian
     PII, a JPEG with EXIF/GPS, a WAV audio clip, a second PDF for a forensic
     report, and a small MP4-extension stand-in for CCTV footage).
  2. Logs in as each demo account and drives the actual endpoints: case
     creation, evidence upload (real SHA-256 hashing + EXIF extraction),
     forensic report upload, integrity verification, PDF redaction (real
     regex-based PII redaction against the text layer), CCTV redaction,
     audio transcription, watermarked download, full-text search (backed by
     the OCR/text-layer pipeline), case lifecycle, court presentation,
     case report generation, user approval, and audit log listing.

Run this AFTER the server is up and seed_data.py has been run once:

    python seed_data.py
    uvicorn app.main:app --reload --port 8000   # in one terminal
    python scripts/populate_demo_data.py         # in another terminal

Requires `httpx` (already suggested by README for the test suite):
    pip install httpx
"""
from __future__ import annotations

import io
import struct
import sys
import time
import wave
from pathlib import Path

import httpx

BASE_URL = "http://127.0.0.1:8000"
DEMO_PASSWORD = "NyayVault@123"
FIXTURES_DIR = Path(__file__).resolve().parent / "demo_fixtures"


# ---------------------------------------------------------------------------
# Step 1: generate real sample files (created fresh each run)
# ---------------------------------------------------------------------------
def _make_witness_statement_pdf(path: Path) -> None:
    """A PDF with a real text layer containing Indian PII, so redact/pdf and
    the OCR text-layer path both have real content to work on."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    lines = [
        "FIR-2026-000341 -- Witness Statement",
        "State vs. Rakesh Malhotra",
        "",
        "Witness: Mr. Suresh Kumar",
        "Aadhaar Number: 1234 5678 9123",
        "Contact Phone: 9876543210",
        "Email: witness.contact@example.com",
        "",
        "Statement: On the night of 12 January 2026, I observed the accused",
        "near the Rajpur Road junction, Dehradun, at approximately 22:40 hrs.",
        "He was travelling in a red motorcycle; the plate was not clearly",
        "visible. I am willing to testify to the above in court.",
    ]
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    y = height - 80
    for line in lines:
        c.drawString(72, y, line)
        y -= 20
    c.save()


def _make_forensic_report_pdf(path: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    lines = [
        "Forensic Examination Report",
        "Case: FIR-2026-000341 -- State vs. Rakesh Malhotra",
        "Examiner: Dr. A. Rao, FS-1042",
        "",
        "Item examined: Seized mobile handset (Exhibit A1)",
        "Finding: Device image acquired via write-blocker; hash verified.",
        "Call log and messages extracted; no signs of tampering detected.",
        "Contact of investigating officer: 9876500011",
    ]
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    y = height - 80
    for line in lines:
        c.drawString(72, y, line)
        y -= 20
    c.save()


def _make_crime_scene_jpeg(path: Path) -> None:
    """A JPEG carrying real EXIF (device + capture time + GPS), matching what
    app/utils/exif_utils.py knows how to read back out."""
    from PIL import Image, ImageDraw
    from PIL.TiffImagePlugin import IFDRational

    img = Image.new("RGB", (900, 600), color=(70, 70, 78))
    draw = ImageDraw.Draw(img)
    draw.text((30, 30), "Evidence Photo -- Rajpur Road junction, Dehradun", fill=(255, 255, 255))
    draw.rectangle([40, 90, 500, 92], fill=(255, 200, 0))

    exif = img.getexif()
    exif[0x010F] = "SampleForensicsCam"       # Make
    exif[0x0110] = "SC-EVID-100"              # Model
    exif[0x0132] = "2026:01:12 22:41:07"      # DateTime

    def dms(deg_float):
        d = int(deg_float)
        m_float = (deg_float - d) * 60
        m = int(m_float)
        s = (m_float - m) * 60
        return (IFDRational(d, 1), IFDRational(m, 1), IFDRational(int(s * 100), 100))

    exif[0x8825] = {
        1: "N", 2: dms(30.3165),   # Dehradun latitude
        3: "E", 4: dms(78.0322),   # Dehradun longitude
    }
    img.save(path, format="JPEG", exif=exif, quality=90)


def _make_audio_clip(path: Path) -> None:
    """A short synthetic WAV clip (no external deps needed) so the audio
    evidence type and /transcribe endpoint both have a real file to open."""
    sample_rate = 16000
    duration_s = 3
    n_samples = sample_rate * duration_s
    freq = 220.0
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n_samples):
            import math

            val = int(3000 * math.sin(2 * math.pi * freq * (i / sample_rate)))
            frames += struct.pack("<h", val)
        wf.writeframes(bytes(frames))


def _make_cctv_stub(path: Path) -> None:
    """Not a decodable video -- just enough bytes, with a .mp4 extension, so
    the upload is classified VIDEO and the CCTV redaction endpoint (which
    only checks doc.type, it doesn't decode frames unless OpenCV is wired
    up) has something to act on."""
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 512)


def generate_fixture_files() -> dict[str, Path]:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    files = {
        "statement_pdf": FIXTURES_DIR / "witness_statement.pdf",
        "forensic_pdf": FIXTURES_DIR / "forensic_report.pdf",
        "photo_jpg": FIXTURES_DIR / "crime_scene.jpg",
        "audio_wav": FIXTURES_DIR / "field_recording.wav",
        "cctv_mp4": FIXTURES_DIR / "junction_cctv.mp4",
    }
    _make_witness_statement_pdf(files["statement_pdf"])
    _make_forensic_report_pdf(files["forensic_pdf"])
    _make_crime_scene_jpeg(files["photo_jpg"])
    _make_audio_clip(files["audio_wav"])
    _make_cctv_stub(files["cctv_mp4"])
    print(f"[fixtures] wrote {len(files)} sample files to {FIXTURES_DIR}")
    return files


# ---------------------------------------------------------------------------
# Step 2: drive the real API
# ---------------------------------------------------------------------------
class ApiSession:
    def __init__(self, client: httpx.Client, username: str, role: str):
        self.client = client
        self.username = username
        self.role = role
        self.token: str | None = None

    def login(self) -> None:
        r = self.client.post(
            "/api/auth/login",
            json={"username": self.username, "password": DEMO_PASSWORD, "role": self.role},
        )
        r.raise_for_status()
        self.token = r.json()["access_token"]
        print(f"[login] {self.username} ({self.role}) OK")

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def get(self, path, **kw):
        return self.client.get(path, headers=self.headers, **kw)

    def post(self, path, **kw):
        return self.client.post(path, headers=self.headers, **kw)


def _check(resp: httpx.Response, what: str):
    if resp.status_code >= 400:
        print(f"  !! {what} -> HTTP {resp.status_code}: {resp.text[:200]}")
        return None
    print(f"  ok  {what} -> {resp.status_code}")
    return resp


def upload_document(sess: ApiSession, case_id: str, file_path: Path, content_type: str) -> str | None:
    with open(file_path, "rb") as fh:
        r = sess.post(
            f"/api/cases/{case_id}/documents",
            files={"file": (file_path.name, fh, content_type)},
        )
    resp = _check(r, f"upload {file_path.name}")
    return resp.json()["id"] if resp else None


def upload_forensic_report(sess: ApiSession, case_id: str, file_path: Path) -> str | None:
    with open(file_path, "rb") as fh:
        r = sess.post(
            f"/api/cases/{case_id}/forensic-reports",
            files={"file": (file_path.name, fh, "application/pdf")},
        )
    resp = _check(r, f"upload forensic report {file_path.name}")
    return resp.json()["id"] if resp else None


def main():
    files = generate_fixture_files()

    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        # Basic reachability check with a friendly error.
        try:
            client.get("/docs")
        except httpx.ConnectError:
            print(f"Could not reach {BASE_URL}. Start the server first:\n"
                  f"  uvicorn app.main:app --reload --port 8000")
            sys.exit(1)

        admin = ApiSession(client, "admin", "admin")
        io_sharma = ApiSession(client, "officer.sharma", "io")
        io_negi = ApiSession(client, "officer.negi", "io")
        forensic_rao = ApiSession(client, "dr.rao", "forensic")
        judge_verma = ApiSession(client, "justice.verma", "judge")

        for s in (admin, io_sharma, io_negi, forensic_rao, judge_verma):
            s.login()

        # --- Admin: approve the pending officer, list users & audit logs ---
        print("\n== Admin: user management ==")
        users = _check(admin.get("/api/users"), "list users").json()
        pending = next((u for u in users if u["username"] == "officer.bhatt"), None)
        if pending and pending["status"] == "pending":
            _check(admin.post(f"/api/users/{pending['id']}/approve"), "approve officer.bhatt")
        else:
            print("  .. officer.bhatt already approved (or not found)")

        # --- IO (officer.sharma): create a new case, upload evidence ---
        print("\n== IO officer.sharma: new case + evidence ==")
        cases = _check(io_sharma.get("/api/cases"), "list my cases").json()
        case_341 = next(c for c in cases if c["number"] == "FIR-2026-000341")
        case_355 = next(c for c in cases if c["number"] == "FIR-2026-000355")

        new_case_resp = io_sharma.post(
            "/api/cases",
            json={"number": "FIR-2026-000501", "title": "State vs. Unknown (Chain Snatching)"},
        )
        new_case = _check(new_case_resp, "create case FIR-2026-000501")
        new_case_id = new_case.json()["id"] if new_case else case_341["id"]

        doc_pdf = upload_document(io_sharma, case_341["id"], files["statement_pdf"], "application/pdf")
        doc_jpg = upload_document(io_sharma, case_341["id"], files["photo_jpg"], "image/jpeg")
        doc_wav = upload_document(io_sharma, case_355["id"], files["audio_wav"], "audio/wav")
        doc_mp4 = upload_document(io_sharma, case_341["id"], files["cctv_mp4"], "video/mp4")

        if doc_pdf:
            _check(io_sharma.get(f"/api/documents/{doc_pdf}"), "view PDF document")
            _check(io_sharma.get(f"/api/documents/{doc_pdf}/blockchain"), "blockchain status (PDF)")
            _check(io_sharma.post(f"/api/documents/{doc_pdf}/redact/pdf"), "redact PII in PDF")
            _check(io_sharma.get(f"/api/documents/{doc_pdf}/download"), "download PDF (watermarked)")
        if doc_mp4:
            _check(io_sharma.post(f"/api/documents/{doc_mp4}/redact/cctv"), "redact CCTV footage")
        if doc_wav:
            _check(io_sharma.post(f"/api/documents/{doc_wav}/transcribe"), "transcribe audio")

        _check(io_sharma.get(f"/api/cases/{case_341['id']}/lifecycle"), "case lifecycle")

        # --- IO officer.negi: separate org scope, should NOT see case_341 ---
        print("\n== IO officer.negi: ABAC scope check (different unit) ==")
        denied = io_negi.get(f"/api/cases/{case_341['id']}")
        if denied.status_code == 403:
            print("  ok  correctly denied access to a case outside their scope (403)")
        else:
            print(f"  !! expected 403, got {denied.status_code}")

        # --- Forensic (dr.rao): forensic report + integrity verification ---
        print("\n== Forensic dr.rao: report upload + verification ==")
        report_doc = upload_forensic_report(forensic_rao, case_341["id"], files["forensic_pdf"])
        if doc_pdf:
            _check(forensic_rao.post(f"/api/documents/{doc_pdf}/verify"), "verify PDF integrity")
        if doc_jpg:
            _check(forensic_rao.post(f"/api/documents/{doc_jpg}/verify"), "verify photo integrity")
        if report_doc:
            _check(forensic_rao.get(f"/api/documents/{report_doc}/download"), "download forensic report")
        _check(forensic_rao.get(f"/api/cases/{case_341['id']}/forensic-reports"), "list forensic reports")
        _check(forensic_rao.get(f"/api/cases/{case_341['id']}/report"), "generate case PDF report")

        # --- Judge Verma: view + present in court ---
        print("\n== Judge justice.verma: review + courtroom presentation ==")
        _check(judge_verma.get(f"/api/cases/{case_341['id']}"), "judge views case")
        _check(judge_verma.post(f"/api/cases/{case_341['id']}/present"), "present case in court")

        # --- Search: give the background OCR task a moment to finish, then search ---
        print("\n== Search (waiting briefly for background OCR) ==")
        time.sleep(2)
        _check(io_sharma.get("/api/search", params={"q": "Rajpur Road"}), 'search "Rajpur Road"')
        _check(io_sharma.get("/api/search", params={"q": "Malhotra"}), 'search "Malhotra"')

        # --- Admin: final audit trail check ---
        print("\n== Admin: audit logs ==")
        _check(admin.get("/api/audit-logs", params={"limit": 20}), "list recent audit logs")

    print("\nDone. Every major feature (upload/hashing, EXIF, OCR, search, "
          "redaction, transcription, watermarked download, forensic reports, "
          "verification, lifecycle, ABAC scope denial, court presentation, "
          "case reports, user approval, audit logs) has now been exercised "
          "through the real API.")


if __name__ == "__main__":
    main()
