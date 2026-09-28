"""
Defence-in-depth for the "lifecycle history is read-only" rule.

The API already exposes no way to edit or delete an audit log row (there are
no PUT / PATCH / DELETE routes on audit logs). This makes that a hard rule at
the ORM layer as well: any code path -- present or future, whatever the
user's role, admin included -- that tries to UPDATE or DELETE an AuditLog
through the ORM raises instead of silently rewriting history.

Scope, honestly: this guards ORM flushes. It does not stop someone with raw
database access. For that, enforce it in the database itself (e.g. on
Postgres: REVOKE UPDATE, DELETE ON audit_logs FROM the app role).

Importing this module is what registers the listeners (see app/main.py).
"""
from sqlalchemy import event

from app.models import AuditLog


class ImmutableAuditLogError(RuntimeError):
    """Raised when something tries to modify or delete an audit log entry."""


@event.listens_for(AuditLog, "before_update")
def _reject_update(mapper, connection, target):
    raise ImmutableAuditLogError("Audit log entries are append-only and cannot be modified.")


@event.listens_for(AuditLog, "before_delete")
def _reject_delete(mapper, connection, target):
    raise ImmutableAuditLogError("Audit log entries are append-only and cannot be deleted.")
