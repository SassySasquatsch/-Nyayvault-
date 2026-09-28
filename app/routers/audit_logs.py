from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.abac import Action, filter_visible_cases, require_case_access
from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models import AuditLog, Case, User
from app.schemas import AuditLogOut

router = APIRouter(prefix="/api/audit-logs", tags=["audit"])


@router.get("", response_model=list[AuditLogOut])
def list_audit_logs(
    request: Request,
    case_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Admins (auditlogs section) get the full, unscoped log.
    Judges (timeline section) may only pull logs scoped to a specific case --
    they should not see department-wide activity.
    IO/forensic have no nav entry for this in the frontend, so we simply
    require a case_id from them too -- with one exception: an IO may omit
    case_id to get recent activity across *their own* authorised cases
    (the IO dashboard's "Recent Activity"). That is still case-scoped data,
    never department-wide.

    ABAC: a non-admin case_id must be a case the caller is authorised for.
    This endpoint is read-only; audit history has no write route at all.
    """
    role_value = user.role.value if hasattr(user.role, "value") else user.role
    q = db.query(AuditLog).order_by(AuditLog.timestamp.desc())

    if role_value != "admin":
        if case_id:
            case = db.query(Case).filter(Case.id == case_id).first()
            if case is None:
                return []
            require_case_access(db, user, case, Action.CASE_AUDIT, request=request)
            q = q.filter(AuditLog.case_id == case_id)
        elif role_value == "io":
            mine = [c.id for c in filter_visible_cases(user, db.query(Case).all(), Action.CASE_AUDIT)]
            if not mine:
                return []
            q = q.filter(AuditLog.case_id.in_(mine))
        else:
            q = q.filter(AuditLog.case_id == "__none__")  # unchanged: must scope to a case
    elif case_id:
        q = q.filter(AuditLog.case_id == case_id)

    return q.limit(limit).all()
