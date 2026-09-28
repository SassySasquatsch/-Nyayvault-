"""
ABAC / organisational-segregation tests.

Run from the project root:

    pip install httpx            # only needed for the tests (FastAPI's TestClient)
    python -m unittest discover -s tests -v

Uses a throw-away SQLite DB + storage dir; your real nyayvault.db is untouched.
"""
import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="nyayvault-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TMP) / 'test.db'}"
os.environ["STORAGE_DIR"] = str(Path(_TMP) / "storage")

from fastapi.testclient import TestClient  # noqa: E402

import seed_data  # noqa: E402  (creates tables in the temp DB)
from app import abac  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AuditAction, AuditLog, Case, User, UserRole  # noqa: E402
from app.utils.audit_guard import ImmutableAuditLogError  # noqa: E402

PW = seed_data.DEMO_PASSWORD


def tearDownModule():
    shutil.rmtree(_TMP, ignore_errors=True)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            seed_data.run()
        cls.client = TestClient(app)
        cls.tokens = {}

    # -- helpers ---------------------------------------------------------
    def login(self, username, role):
        if username not in self.tokens:
            r = self.client.post("/api/auth/login", json={"username": username, "password": PW, "role": role})
            self.assertEqual(r.status_code, 200, r.text)
            self.tokens[username] = {"Authorization": f"Bearer {r.json()['access_token']}"}
        return self.tokens[username]

    def h(self, who):
        who = "admin" if who == "admin.x" else who
        return self.login(who, {"officer": "io", "dr": "forensic", "justice": "judge", "admin": "admin"}[who.split(".")[0]])

    def case_id(self, number):
        db = SessionLocal()
        try:
            return db.query(Case).filter(Case.number == number).one().id
        finally:
            db.close()

    def upload(self, who, number, name="statement.pdf", data=b"%PDF-1.4 test"):
        return self.client.post(f"/api/cases/{self.case_id(number)}/documents", headers=self.h(who),
                                files={"file": (name, data, "application/pdf")})

    def numbers(self, who):
        r = self.client.get("/api/cases", headers=self.h(who))
        self.assertEqual(r.status_code, 200)
        return {c["number"] for c in r.json()}


UK_A = {"FIR-2026-000341", "FIR-2026-000298", "FIR-2026-000187", "FIR-2026-000355"}
UK_B = "FIR-2026-000402"
MH_B = "FIR-2026-000412"


class TestScopeAndOwnership(Base):
    def test_case_list_is_segregated(self):
        self.assertTrue(UK_A <= self.numbers("officer.sharma"))
        self.assertNotIn(UK_B, self.numbers("officer.sharma"))
        self.assertNotIn(MH_B, self.numbers("officer.sharma"))
        self.assertEqual(self.numbers("officer.negi") & {UK_B, MH_B, *UK_A}, {UK_B})
        self.assertEqual(self.numbers("officer.kulkarni") & {UK_B, MH_B, *UK_A}, {MH_B})
        # forensic / judge: unit wildcard -> whole district, but not another state
        self.assertTrue((UK_A | {UK_B}) <= self.numbers("dr.rao"))
        self.assertNotIn(MH_B, self.numbers("dr.rao"))
        self.assertEqual(self.numbers("dr.deshmukh") & {UK_B, MH_B, *UK_A}, {MH_B})
        self.assertTrue((UK_A | {UK_B}) <= self.numbers("justice.verma"))
        self.assertNotIn(MH_B, self.numbers("justice.verma"))
        # admin = org-wide oversight
        self.assertTrue((UK_A | {UK_B, MH_B}) <= self.numbers("admin"))

    def test_io_cannot_open_other_state_or_other_unit_case(self):
        for number in (MH_B, UK_B):            # other state, and same district but Unit B
            cid = self.case_id(number)
            h = self.h("officer.sharma")
            self.assertEqual(self.client.get(f"/api/cases/{cid}", headers=h).status_code, 403)
            self.assertEqual(self.client.get(f"/api/cases/{cid}/documents", headers=h).status_code, 403)
            self.assertEqual(self.client.get(f"/api/cases/{cid}/lifecycle", headers=h).status_code, 403)
            self.assertEqual(self.client.get(f"/api/audit-logs?case_id={cid}", headers=h).status_code, 403)
            r = self.client.post(f"/api/cases/{cid}/documents", headers=h, files={"file": ("x.pdf", b"x", "application/pdf")})
            self.assertEqual(r.status_code, 403)

    def test_io_can_open_own_unit_case(self):
        cid = self.case_id("FIR-2026-000341")
        h = self.h("officer.sharma")
        self.assertEqual(self.client.get(f"/api/cases/{cid}", headers=h).status_code, 200)
        self.assertEqual(self.client.get(f"/api/cases/{cid}/lifecycle", headers=h).status_code, 200)

    def test_same_scope_but_not_assigned_is_denied_for_io(self):
        """officer.bhatt has the same state/district/unit as sharma but does not own the case."""
        self.client.post(f"/api/users/{self._user_id('officer.bhatt')}/approve", headers=self.h("admin.x"))
        r = self.client.post("/api/auth/login", json={"username": "officer.bhatt", "password": PW, "role": "io"})
        self.assertEqual(r.status_code, 200, r.text)
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        self.assertEqual(self.client.get("/api/cases", headers=h).json(), [])
        cid = self.case_id("FIR-2026-000341")
        self.assertEqual(self.client.get(f"/api/cases/{cid}", headers=h).status_code, 403)
        self.assertEqual(self.client.get(f"/api/cases/{cid}/lifecycle", headers=h).status_code, 403)

    def _user_id(self, username):
        db = SessionLocal()
        try:
            return db.query(User).filter(User.username == username).one().id
        finally:
            db.close()

    def test_case_insensitive_scope_match(self):
        db = SessionLocal()
        try:
            u = db.query(User).filter(User.username == "dr.rao").one()
            u.state = "  UTTARAKHAND "
            db.commit()
        finally:
            db.close()
        self.assertIn("FIR-2026-000341", self.numbers("dr.rao"))


class TestDocumentsEvidenceSearch(Base):
    def test_documents_evidence_search_follow_the_case_scope(self):
        r = self.upload("officer.sharma", "FIR-2026-000341", name="malhotra_statement.pdf")
        self.assertEqual(r.status_code, 201, r.text)
        doc = r.json()
        r2 = self.upload("officer.kulkarni", MH_B, name="cargo_manifest.pdf", data=b"%PDF-1.4 mh")
        self.assertEqual(r2.status_code, 201, r2.text)
        mh_doc = r2.json()

        # documents: own scope OK, foreign scope denied - on every doc endpoint
        for path, method in ((f"/api/documents/{mh_doc['id']}", "get"),
                             (f"/api/documents/{mh_doc['id']}/download", "get"),
                             (f"/api/documents/{mh_doc['id']}/blockchain", "get"),
                             (f"/api/documents/{mh_doc['id']}/verify", "post"),
                             (f"/api/documents/{mh_doc['id']}/redact/pdf", "post")):
            resp = getattr(self.client, method)(path, headers=self.h("officer.sharma"))
            self.assertEqual(resp.status_code, 403, f"{method} {path}")
        self.assertEqual(self.client.get(f"/api/documents/{doc['id']}/download", headers=self.h("officer.sharma")).status_code, 200)

        # evidence integrity check: forensic of the same scope yes, other state no
        self.assertEqual(self.client.post(f"/api/documents/{doc['id']}/verify", headers=self.h("dr.rao")).status_code, 200)
        self.assertEqual(self.client.post(f"/api/documents/{doc['id']}/verify", headers=self.h("dr.deshmukh")).status_code, 403)
        self.assertEqual(self.client.post(f"/api/documents/{mh_doc['id']}/verify", headers=self.h("dr.rao")).status_code, 403)
        self.assertEqual(self.client.post(f"/api/documents/{mh_doc['id']}/verify", headers=self.h("dr.deshmukh")).status_code, 200)

        # search: results never cross the boundary (by title, doc name, or hash)
        def hits(who, q):
            resp = self.client.get("/api/search", params={"q": q}, headers=self.h(who))
            self.assertEqual(resp.status_code, 200)
            return resp.json()
        self.assertTrue(hits("officer.sharma", "malhotra"))
        self.assertEqual(hits("officer.kulkarni", "malhotra"), [])
        self.assertEqual(hits("officer.sharma", "cargo"), [])
        self.assertEqual(hits("officer.sharma", mh_doc["hash_sha256"][:12]), [])
        self.assertTrue(hits("officer.kulkarni", "cargo"))
        self.assertTrue(hits("admin.x", "cargo"))

    def test_report_and_court_present_are_scoped(self):
        mh = self.case_id(MH_B)
        uk = self.case_id("FIR-2026-000341")
        self.assertEqual(self.client.get(f"/api/cases/{mh}/report", headers=self.h("dr.rao")).status_code, 403)
        self.assertEqual(self.client.post(f"/api/cases/{mh}/present", headers=self.h("justice.verma")).status_code, 403)
        self.assertEqual(self.client.post(f"/api/cases/{uk}/present", headers=self.h("justice.verma")).status_code, 200)

    def test_evidence_is_not_served_as_public_static_files(self):
        r = self.upload("officer.sharma", "FIR-2026-000341", name="pub.pdf", data=b"%PDF-1.4 pub")
        self.assertEqual(r.status_code, 201)
        rel = Path(settings.EVIDENCE_DIR).relative_to(settings.STORAGE_DIR)
        self.assertEqual(self.client.get(f"/files/{rel}/{self.case_id('FIR-2026-000341')}/x").status_code, 404)
        self.assertEqual(self.client.get("/files/evidence/").status_code, 404)


class TestAddCase(Base):
    def test_creator_becomes_owner_and_scope_is_stamped_from_their_attributes(self):
        h = self.h("officer.sharma")
        r = self.client.post("/api/cases", headers=h, json={
            "number": "FIR-2026-900001", "title": "  State vs. Test  ",
            "state": "Maharashtra", "district": "Mumbai", "unit": "Unit B", "owner_id": "usr_someoneelse"})
        self.assertEqual(r.status_code, 201, r.text)
        c = r.json()
        self.assertEqual((c["state"], c["district"], c["unit"]), ("Uttarakhand", "Dehradun", "Unit A"))
        self.assertEqual(c["owner_id"], self._me("officer.sharma"))
        self.assertEqual(c["status"], "active")
        self.assertEqual(c["title"], "State vs. Test")
        self.assertIn("FIR-2026-900001", self.numbers("officer.sharma"))
        self.assertNotIn("FIR-2026-900001", self.numbers("officer.kulkarni"))
        # the existing audit event is written
        db = SessionLocal()
        try:
            rows = db.query(AuditLog).filter(AuditLog.case_id == c["id"], AuditLog.action == AuditAction.case_create).all()
            self.assertEqual(len(rows), 1)
        finally:
            db.close()

    def _me(self, username):
        return self.client.get("/api/auth/me", headers=self.h(username)).json()["id"]

    def test_validation_duplicates_and_rbac(self):
        h = self.h("officer.sharma")
        self.assertEqual(self.client.post("/api/cases", headers=h, json={"number": "FIR-2026-000341", "title": "dup"}).status_code, 400)
        self.assertEqual(self.client.post("/api/cases", headers=h, json={"number": "  ", "title": "x"}).status_code, 422)
        self.assertEqual(self.client.post("/api/cases", headers=h, json={"number": "N1", "title": ""}).status_code, 422)
        # RBAC unchanged: only IOs open cases
        self.assertEqual(self.client.post("/api/cases", headers=self.h("dr.rao"), json={"number": "Z1", "title": "t"}).status_code, 403)

    def test_io_without_scope_cannot_open_cases(self):
        self.client.post("/api/users", headers=self.h("admin.x"),
                         json={"full_name": "No Scope", "username": "officer.noscope", "badge_id": "IO-0000",
                               "role": "io", "password": PW})
        uid = self._uid("officer.noscope")
        self.client.post(f"/api/users/{uid}/approve", headers=self.h("admin.x"))
        r = self.client.post("/api/auth/login", json={"username": "officer.noscope", "password": PW, "role": "io"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        self.assertEqual(self.client.post("/api/cases", headers=h, json={"number": "FIR-2026-900002", "title": "t"}).status_code, 403)
        self.assertEqual(self.client.get("/api/cases", headers=h).json(), [])

    def _uid(self, username):
        db = SessionLocal()
        try:
            return db.query(User).filter(User.username == username).one().id
        finally:
            db.close()

    def test_any_state_works_nothing_is_hard_coded(self):
        adm = self.h("admin.x")
        for uname, badge, scope in (("officer.nair", "IO-7001", ("Kerala", "Kochi", "Cyber Cell")),
                                    ("officer.rao2", "IO-7002", ("Kerala", "Kochi", "Narcotics"))):
            r = self.client.post("/api/users", headers=adm, json={
                "full_name": uname, "username": uname, "badge_id": badge, "role": "io", "password": PW,
                "state": scope[0], "district": scope[1], "unit": scope[2]})
            self.assertEqual(r.status_code, 201, r.text)
            self.client.post(f"/api/users/{r.json()['user']['id']}/approve", headers=adm)
        def tok(u):
            return {"Authorization": "Bearer " + self.client.post("/api/auth/login", json={"username": u, "password": PW, "role": "io"}).json()["access_token"]}
        a, b = tok("officer.nair"), tok("officer.rao2")
        c = self.client.post("/api/cases", headers=a, json={"number": "FIR-2026-900003", "title": "Kerala case"}).json()
        self.assertEqual((c["state"], c["unit"]), ("Kerala", "Cyber Cell"))
        self.assertEqual(self.client.get(f"/api/cases/{c['id']}", headers=a).status_code, 200)
        self.assertEqual(self.client.get(f"/api/cases/{c['id']}", headers=b).status_code, 403)


class TestPolicyEngineIsConfigurable(Base):
    """evaluate() reads its rules from settings, so segregation levels and
    exemptions are configuration, not code."""

    def _objs(self):
        db = SessionLocal()
        try:
            case = db.query(Case).filter(Case.number == "FIR-2026-000341").one()
            rao = db.query(User).filter(User.username == "dr.rao").one()
            db.expunge_all()
            return case, rao
        finally:
            db.close()

    def test_drop_district_and_unit_from_scope(self):
        case, rao = self._objs()
        rao.district, rao.unit = "Some Other District", "Some Other Unit"
        self.assertFalse(abac.evaluate(rao, case, abac.Action.CASE_READ).allowed)
        old = abac.SCOPE_ATTRIBUTES
        try:
            abac.SCOPE_ATTRIBUTES = ("state",)
            self.assertTrue(abac.evaluate(rao, case, abac.Action.CASE_READ).allowed)
        finally:
            abac.SCOPE_ATTRIBUTES = old

    def test_document_type_rule_from_config(self):
        db = SessionLocal()
        try:
            case = db.query(Case).filter(Case.number == "FIR-2026-000341").one()
            rao = db.query(User).filter(User.username == "dr.rao").one()
            from app.models import Document, DocType
            vid = Document(case_id=case.id, name="v.mp4", type=DocType.VIDEO, file_path="x", hash_sha256="0" * 64)
            pdf = Document(case_id=case.id, name="p.pdf", type=DocType.PDF, file_path="x", hash_sha256="1" * 64)
            settings.ABAC_ROLE_DOC_TYPES["forensic"] = ["PDF"]
            try:
                self.assertFalse(abac.evaluate(rao, case, abac.Action.DOC_VERIFY, vid).allowed)
                self.assertTrue(abac.evaluate(rao, case, abac.Action.DOC_VERIFY, pdf).allowed)
            finally:
                settings.ABAC_ROLE_DOC_TYPES.pop("forensic", None)
        finally:
            db.close()

    def test_missing_user_attribute_fails_closed(self):
        case, rao = self._objs()
        rao.state, rao.district, rao.unit = None, None, None
        self.assertFalse(abac.evaluate(rao, case, abac.Action.CASE_READ).allowed)

    def test_bad_config_is_rejected(self):
        old = settings.ABAC_SCOPE_ATTRIBUTES
        settings.ABAC_SCOPE_ATTRIBUTES = ("state", "planet")
        try:
            with self.assertRaises(RuntimeError):
                abac._validate_config()
        finally:
            settings.ABAC_SCOPE_ATTRIBUTES = old


class TestRecentActivityAndOverview(Base):
    def test_io_recent_activity_only_covers_own_authorised_cases(self):
        self.upload("officer.sharma", "FIR-2026-000341", name="ra.pdf", data=b"%PDF-1.4 ra")
        self.upload("officer.kulkarni", MH_B, name="ra_mh.pdf", data=b"%PDF-1.4 ra-mh")
        ids = {c["id"] for c in self.client.get("/api/cases", headers=self.h("officer.sharma")).json()}
        rows = self.client.get("/api/audit-logs", headers=self.h("officer.sharma")).json()
        self.assertTrue(rows)
        self.assertTrue(all(r["case_id"] in ids for r in rows))
        mh_rows = self.client.get("/api/audit-logs", headers=self.h("officer.kulkarni")).json()
        self.assertTrue(all(r["case_id"] not in ids for r in mh_rows))
        # non-IO, non-admin roles keep the old rule: a case_id is required
        self.assertEqual(self.client.get("/api/audit-logs", headers=self.h("dr.rao")).json(), [])

    def test_case_out_has_activity_and_owner_fields(self):
        self.upload("officer.sharma", "FIR-2026-000341", name="lastact.pdf", data=b"%PDF-1.4 la")
        c = {c["number"]: c for c in self.client.get("/api/cases", headers=self.h("officer.sharma")).json()}["FIR-2026-000341"]
        self.assertIsNotNone(c["last_activity"])
        self.assertEqual(c["owner_name"], "Insp. R. Sharma")
        self.assertGreaterEqual(c["doc_count"], 1)

    def test_overview_counts_are_scoped(self):
        s = self.client.get("/api/cases/overview/summary", headers=self.h("officer.sharma")).json()
        k = self.client.get("/api/cases/overview/summary", headers=self.h("officer.kulkarni")).json()
        a = self.client.get("/api/cases/overview/summary", headers=self.h("admin.x")).json()
        self.assertGreater(a["evidence_items"], 0)
        self.assertLessEqual(s["evidence_items"] + k["evidence_items"], a["evidence_items"])
        self.assertLess(k["active_cases"], a["active_cases"])


class TestDenialsAreAuditedAndHistoryIsReadOnly(Base):
    def test_denied_access_is_written_to_the_audit_log(self):
        cid = self.case_id(MH_B)
        self.client.get(f"/api/cases/{cid}", headers=self.h("officer.sharma"))
        logs = self.client.get("/api/audit-logs", headers=self.h("admin.x")).json()
        self.assertTrue(any(l["action"] == "access_denied" and l["case_id"] == cid for l in logs))
        # the owning IO can see the attempt in the case lifecycle...
        lc = self.client.get(f"/api/cases/{cid}/lifecycle", headers=self.h("officer.kulkarni")).json()
        self.assertTrue(any(e["action"] == "access_denied" for e in lc["events"]))
        # ...but it does not count as case activity
        c = {c["number"]: c for c in self.client.get("/api/cases", headers=self.h("officer.kulkarni")).json()}[MH_B]
        latest_real = max(e["timestamp"] for e in lc["events"] if e["action"] != "access_denied") if any(e["action"] != "access_denied" for e in lc["events"]) else None
        if latest_real:
            self.assertLessEqual(c["last_activity"][:19], latest_real[:19])

    def test_lifecycle_and_audit_have_no_write_routes_for_any_role(self):
        cid = self.case_id("FIR-2026-000341")
        for who in ("officer.sharma", "dr.rao", "justice.verma", "admin.x"):
            h = self.h(who)
            for method in ("post", "put", "patch", "delete"):
                for path in (f"/api/cases/{cid}/lifecycle", "/api/audit-logs"):
                    r = getattr(self.client, method)(path, headers=h)
                    self.assertIn(r.status_code, (404, 405), f"{who} {method} {path} -> {r.status_code}")

    def test_orm_refuses_to_edit_or_delete_history_even_for_admin_code_paths(self):
        db = SessionLocal()
        try:
            row = db.query(AuditLog).first()
            row.detail = "tampered"
            with self.assertRaises(ImmutableAuditLogError):
                db.commit()
            db.rollback()
            db.delete(db.query(AuditLog).first())
            with self.assertRaises(ImmutableAuditLogError):
                db.commit()
            db.rollback()
        finally:
            db.close()


class TestMigration(unittest.TestCase):
    def test_upgrades_an_existing_database_in_place(self):
        from sqlalchemy import create_engine, text
        from app.database import ensure_abac_schema
        eng = create_engine(f"sqlite:///{Path(_TMP) / 'old.db'}")
        with eng.begin() as c:
            c.execute(text("CREATE TABLE users (id VARCHAR PRIMARY KEY, username VARCHAR)"))
            c.execute(text("CREATE TABLE cases (id VARCHAR PRIMARY KEY, number VARCHAR, created_by_id VARCHAR)"))
            c.execute(text("INSERT INTO users VALUES ('u1','sharma')"))
            c.execute(text("INSERT INTO cases VALUES ('c1','FIR-1','u1')"))
        ensure_abac_schema(eng)
        ensure_abac_schema(eng)      # idempotent
        with eng.begin() as c:
            c.execute(text("UPDATE users SET state='S', district='D', unit='U' WHERE id='u1'"))
            c.execute(text("UPDATE cases SET state=NULL"))
        ensure_abac_schema(eng)
        with eng.connect() as c:
            row = c.execute(text("SELECT owner_id, state, district, unit FROM cases WHERE id='c1'")).one()
        self.assertEqual(tuple(row), ("u1", "S", "D", "U"))


# ---------------------------------------------------------------------------
# MVP cleanup: FIR number format + forensic report upload
# ---------------------------------------------------------------------------
class TestFirNumberFormat(Base):
    def _create(self, number):
        return self.client.post("/api/cases", headers=self.h("officer.sharma"),
                                json={"number": number, "title": "FIR format test"})

    def test_valid_format_is_accepted(self):
        r = self._create("FIR-2026-445566")
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["number"], "FIR-2026-445566")

    def test_surrounding_whitespace_is_trimmed_not_rejected(self):
        r = self._create("  FIR-2026-445577  ")
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["number"], "FIR-2026-445577")

    def test_invalid_formats_are_rejected(self):
        for bad in ("ABC123", "N1", "FIR-2026-0341", "FIR-MH-2026-0412", "FIR-2026-44556",
                    "FIR-2026-4455667", "fir-2026-445566", "FIR-26-445566", "FIR-2026-44556A",
                    "FIR 2026 445566", "FIR-2026-445566-1"):
            r = self._create(bad)
            self.assertEqual(r.status_code, 422, f"{bad!r} -> {r.status_code}")
            self.assertIn("FIR-YYYY-NNNNNN", r.text)

    def test_existing_cases_with_the_old_format_still_work(self):
        """Validation applies to new cases only: nothing already stored is re-checked."""
        db = SessionLocal()
        try:
            owner = db.query(User).filter(User.username == "officer.sharma").one()
            db.add(Case(number="FIR-2026-0999", title="legacy", created_by_id=owner.id, owner_id=owner.id,
                        state=owner.state, district=owner.district, unit=owner.unit))
            db.commit()
        finally:
            db.close()
        cid = self.case_id("FIR-2026-0999")
        h = self.h("officer.sharma")
        self.assertEqual(self.client.get(f"/api/cases/{cid}", headers=h).status_code, 200)
        self.assertEqual(self.client.get(f"/api/cases/{cid}/lifecycle", headers=h).status_code, 200)
        self.assertEqual(self.upload("officer.sharma", "FIR-2026-0999", name="legacy.pdf").status_code, 201)


class TestForensicReports(Base):
    CASE = "FIR-2026-000341"          # Uttarakhand / Dehradun / Unit A, owned by officer.sharma
    OTHER_STATE = "FIR-2026-000412"   # Maharashtra / Mumbai / Unit B

    def report(self, who, number, name="exam_report.pdf", data=b"%PDF-1.4 forensic exam report",
               ctype="application/pdf"):
        return self.client.post(f"/api/cases/{self.case_id(number)}/forensic-reports", headers=self.h(who),
                                files={"file": (name, data, ctype)})

    def test_forensic_officer_uploads_report_with_hash_uploader_and_timestamp(self):
        import hashlib
        data = b"%PDF-1.4 forensic exam report body"
        r = self.report("dr.rao", self.CASE, data=data)
        self.assertEqual(r.status_code, 201, r.text)
        d = r.json()
        self.assertEqual(d["category"], "forensic_report")
        self.assertEqual(d["hash_sha256"], hashlib.sha256(data).hexdigest())     # generated server-side
        self.assertEqual(d["uploader_name"], "Dr. A. Rao")
        self.assertTrue(d["uploaded_at"])
        self.assertEqual(d["status"], "verified")

        # the stored file really has the recorded hash (the existing integrity check passes)
        v = self.client.post(f"/api/documents/{d['id']}/verify", headers=self.h("dr.rao"))
        self.assertEqual(v.status_code, 200, v.text)
        self.assertTrue(v.json()["match"])

    def test_report_is_written_to_the_audit_trail_and_document_lifecycle(self):
        d = self.report("dr.rao", self.CASE, name="lifecycle_report.pdf", data=b"%PDF-1.4 lc").json()
        cid = self.case_id(self.CASE)
        for who in ("officer.sharma", "dr.rao", "justice.verma", "admin.x"):
            lc = self.client.get(f"/api/cases/{cid}/lifecycle", headers=self.h(who)).json()
            hits = [e for e in lc["events"] if e["action"] == "forensic_report_upload" and e["document_id"] == d["id"]]
            self.assertEqual(len(hits), 1, who)
            self.assertEqual(hits[0]["stage"], "report")
            self.assertEqual(hits[0]["hash_sha256"], d["hash_sha256"])
            self.assertEqual(hits[0]["integrity_status"], "hash_recorded")
        # the forensic officer's document-only lifecycle view includes it too
        one = self.client.get(f"/api/cases/{cid}/lifecycle?document_id={d['id']}", headers=self.h("dr.rao")).json()
        self.assertTrue(any(e["action"] == "forensic_report_upload" for e in one["events"]))
        # and it is in the audit log with the hash in the detail
        logs = self.client.get("/api/audit-logs", headers=self.h("admin.x")).json()
        self.assertTrue(any(l["action"] == "forensic_report_upload" and d["hash_sha256"] in l["detail"] for l in logs))

    def test_only_forensic_role_can_upload_reports(self):
        for who in ("officer.sharma", "justice.verma", "admin.x"):
            self.assertEqual(self.report(who, self.CASE).status_code, 403, who)
        r = self.client.post(f"/api/cases/{self.case_id(self.CASE)}/forensic-reports",
                             files={"file": ("x.pdf", b"x", "application/pdf")})
        self.assertEqual(r.status_code, 401)

    def test_forensic_officer_outside_scope_is_denied_and_audited(self):
        r = self.report("dr.rao", self.OTHER_STATE)              # Uttarakhand forensic -> Maharashtra case
        self.assertEqual(r.status_code, 403)
        r = self.report("dr.deshmukh", self.CASE)                # Maharashtra forensic -> Uttarakhand case
        self.assertEqual(r.status_code, 403)
        logs = self.client.get("/api/audit-logs", headers=self.h("admin.x")).json()
        self.assertTrue(any(l["action"] == "access_denied" and "doc:upload_forensic_report" in l["detail"] for l in logs))

    def test_only_pdf_doc_docx_are_accepted(self):
        self.assertEqual(self.report("dr.rao", self.CASE, name="a.docx", data=b"PK docx",
                                     ctype="application/vnd.openxmlformats-officedocument.wordprocessingml.document").status_code, 201)
        self.assertEqual(self.report("dr.rao", self.CASE, name="b.doc", data=b"doc", ctype="application/msword").status_code, 201)
        for name in ("evil.exe", "photo.jpg", "notes.txt", "noext"):
            self.assertEqual(self.report("dr.rao", self.CASE, name=name, data=b"x", ctype="application/octet-stream").status_code,
                             400, name)
        self.assertIn(self.report("dr.rao", self.CASE, name="empty.pdf", data=b"").status_code, (400, 422))

    def test_report_access_follows_rbac_and_abac(self):
        d = self.report("dr.rao", self.CASE, name="access_report.pdf", data=b"%PDF-1.4 access").json()
        cid = self.case_id(self.CASE)
        # authorised: assigned IO, same-scope forensic, judge, admin
        for who in ("officer.sharma", "dr.rao", "justice.verma", "admin.x"):
            self.assertEqual(self.client.get(f"/api/documents/{d['id']}", headers=self.h(who)).status_code, 200, who)
            self.assertEqual(self.client.get(f"/api/documents/{d['id']}/download", headers=self.h(who)).status_code, 200, who)
            listed = self.client.get(f"/api/cases/{cid}/forensic-reports", headers=self.h(who))
            self.assertEqual(listed.status_code, 200, who)
            self.assertIn(d["id"], {x["id"] for x in listed.json()})
        # not authorised: other state (forensic / IO), other unit (IO), and anonymous
        for who in ("dr.deshmukh", "officer.kulkarni", "officer.negi"):
            self.assertEqual(self.client.get(f"/api/documents/{d['id']}", headers=self.h(who)).status_code, 403, who)
            self.assertEqual(self.client.get(f"/api/documents/{d['id']}/download", headers=self.h(who)).status_code, 403, who)
            self.assertEqual(self.client.get(f"/api/cases/{cid}/forensic-reports", headers=self.h(who)).status_code, 403, who)
        self.assertEqual(self.client.get(f"/api/documents/{d['id']}/download").status_code, 401)

    def test_reports_are_not_mixed_into_evidence_and_evidence_upload_cannot_fake_a_report(self):
        cid = self.case_id(self.CASE)
        ev = self.upload("officer.sharma", self.CASE, name="plain_statement.pdf", data=b"%PDF-1.4 plain").json()
        self.assertEqual(ev["category"], "evidence")
        # the generic endpoint ignores a client-supplied category
        r = self.client.post(f"/api/cases/{cid}/documents", headers=self.h("dr.rao"),
                             data={"category": "forensic_report"},
                             files={"file": ("sneaky.pdf", b"%PDF-1.4 sneaky", "application/pdf")})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["category"], "evidence")
        reports = self.client.get(f"/api/cases/{cid}/forensic-reports", headers=self.h("dr.rao")).json()
        self.assertNotIn(ev["id"], {x["id"] for x in reports})
        self.assertNotIn(r.json()["id"], {x["id"] for x in reports})
        # case detail exposes the category so the UI can tell them apart
        detail = self.client.get(f"/api/cases/{cid}", headers=self.h("officer.sharma")).json()
        cats = {d["id"]: d["category"] for d in detail["documents"]}
        self.assertEqual(cats[ev["id"]], "evidence")

    def test_document_details_expose_uploader_and_metadata_for_the_details_view(self):
        d = self.upload("officer.sharma", self.CASE, name="details.pdf", data=b"%PDF-1.4 details").json()
        got = self.client.get(f"/api/documents/{d['id']}", headers=self.h("justice.verma")).json()
        self.assertEqual(got["uploader_name"], "Insp. R. Sharma")
        self.assertEqual(set(got["exif"]), {"device", "gps", "imei", "created"})
        self.assertIn("blockchain_tx_hash", got)

    def test_redaction_and_transcription_backend_endpoints_are_still_mounted(self):
        d = self.upload("officer.sharma", self.CASE, name="redact_me.pdf", data=b"%PDF-1.4 redact").json()
        r = self.client.post(f"/api/documents/{d['id']}/redact/pdf", headers=self.h("officer.sharma"))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.client.get(f"/api/cases/{self.case_id(self.CASE)}/report", headers=self.h("dr.rao")).status_code, 200)

    def test_forensic_report_lifecycle_and_audit_stay_read_only(self):
        cid = self.case_id(self.CASE)
        for method in ("put", "patch", "delete"):
            r = getattr(self.client, method)(f"/api/cases/{cid}/forensic-reports", headers=self.h("dr.rao"))
            self.assertIn(r.status_code, (404, 405), method)


class TestDocumentCategoryMigration(unittest.TestCase):
    def test_adds_category_to_an_existing_documents_table_and_backfills(self):
        from sqlalchemy import create_engine, text
        from app.database import ensure_document_category_schema
        eng = create_engine(f"sqlite:///{Path(_TMP) / 'old_docs.db'}")
        with eng.begin() as c:
            c.execute(text("CREATE TABLE documents (id VARCHAR PRIMARY KEY, name VARCHAR)"))
            c.execute(text("INSERT INTO documents VALUES ('d1','a.pdf')"))
        ensure_document_category_schema(eng)
        ensure_document_category_schema(eng)      # idempotent
        with eng.connect() as c:
            self.assertEqual(c.execute(text("SELECT category FROM documents WHERE id='d1'")).scalar(), "evidence")

    def test_is_a_noop_when_there_is_no_documents_table(self):
        from sqlalchemy import create_engine
        from app.database import ensure_document_category_schema
        ensure_document_category_schema(create_engine(f"sqlite:///{Path(_TMP) / 'empty.db'}"))


if __name__ == "__main__":
    unittest.main()
