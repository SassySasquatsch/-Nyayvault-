"""
Document categories and the two small validators that go with them.

Kept free of any FastAPI / SQLAlchemy imports so the models, schemas, routers
and the (unit-testable) lifecycle builder can all share one definition.

A document is either ordinary case material ("evidence" -- the default for
everything uploaded through POST /api/cases/{id}/documents) or a forensic
examination report ("forensic_report" -- only ever created through
POST /api/cases/{id}/forensic-reports by a forensic officer).
"""
import re
from pathlib import Path
from typing import Optional

DOC_CATEGORY_EVIDENCE = "evidence"
DOC_CATEGORY_FORENSIC_REPORT = "forensic_report"
DOC_CATEGORY_COURT_ORDER = "court_order"

# File types a forensic report may be uploaded as.
FORENSIC_REPORT_EXTENSIONS = (".pdf", ".doc", ".docx")

# File types a court order / judgment may be uploaded as. Same shape as a
# forensic report -- a scanned or word-processed legal document.
COURT_ORDER_EXTENSIONS = (".pdf", ".doc", ".docx")

# FIR / case numbers: FIR-YYYY-NNNNNN, e.g. FIR-2026-445566.
# Four-digit year (19xx / 20xx) and exactly six digits. Anything else
# (ABC123, N1, FIR-2026-0341, FIR-MH-2026-0412, ...) is rejected.
FIR_NUMBER_RE = re.compile(r"^FIR-(?:19|20)\d{2}-\d{6}$")
FIR_NUMBER_MESSAGE = "FIR number must be in the format FIR-YYYY-NNNNNN (for example FIR-2026-445566)."


def is_valid_fir_number(value: Optional[str]) -> bool:
    return bool(value) and FIR_NUMBER_RE.fullmatch(value) is not None


def is_forensic_report_category(category: Optional[str]) -> bool:
    return category == DOC_CATEGORY_FORENSIC_REPORT


def has_forensic_report_extension(filename: Optional[str]) -> bool:
    return Path(filename or "").suffix.lower() in FORENSIC_REPORT_EXTENSIONS


def is_court_order_category(category: Optional[str]) -> bool:
    return category == DOC_CATEGORY_COURT_ORDER


def has_court_order_extension(filename: Optional[str]) -> bool:
    return Path(filename or "").suffix.lower() in COURT_ORDER_EXTENSIONS
