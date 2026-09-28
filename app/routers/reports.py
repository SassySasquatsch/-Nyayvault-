from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.abac import Action, get_authorised_case
from app.database import get_db
from app.dependencies import get_client_ip, log_audit, require_roles
from app.models import AuditAction, Case, User
from app.utils.pdf_report import build_case_report

router = APIRouter(prefix="/api/cases", tags=["reports"])


@router.get("/{case_id}/report")
def generate_report(
    case_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("forensic", "admin")),
):
    case = get_authorised_case(db, user, case_id, Action.CASE_REPORT, request=request)

    pdf_path = build_case_report(case)

    log_audit(
        db,
        action=AuditAction.report,
        detail=f"'{user.username}' generated the evidence report for {case.number}",
        user=user,
        ip_address=get_client_ip(request),
        case_id=case.id,
    )
    return FileResponse(
        path=pdf_path, filename=f"{case.number}.pdf", media_type="application/pdf"
    )
