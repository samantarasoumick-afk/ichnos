from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def log_audit_event(
    db: Session,
    organization_id: str,
    action: str,
    actor_user_id: str | None = None,
    actor_email: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: str | None = None,
) -> None:
    """
    Record an audit event. Deliberately does not commit - callers add
    this to the same transaction as the action being logged, so the
    audit entry and the action it describes succeed or fail together
    rather than the log silently missing a write that did happen (or
    recording one that got rolled back).
    """

    db.add(
        AuditLog(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            details=details,
        )
    )
