from .models import AuditLog

def log_action(user, society, action, target=None, details=None, request=None):
    """
    Registra un'azione effettuata da un utente.
    """
    ip_address = None
    if request:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0]
        else:
            ip_address = request.META.get('REMOTE_ADDR')

    target_id = None
    target_type = None
    if target:
        target_id = str(target.pk)
        target_type = target.__class__.__name__

    AuditLog.objects.create(
        user=user,
        society=society,
        action=action,
        target_id=target_id,
        target_type=target_type,
        details=details or {},
        ip_address=ip_address
    )
