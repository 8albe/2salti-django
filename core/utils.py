from datetime import timedelta
from django.utils import timezone

def get_calendar_dates(center_date=None, days_before=7, days_after=14):
    """
    Genera una lista di date centrate su center_date (default: oggi).
    Restituisce una lista di oggetti datetime.date.
    """
    if center_date is None:
        center_date = timezone.now().date()
        
    start_date = center_date - timedelta(days=days_before)
    total_days = days_before + days_after + 1
    
    dates = [start_date + timedelta(days=i) for i in range(total_days)]
    return dates

def mask_email(email: str) -> str:
    """Maschera un'email: a***@example.com"""
    if not email or "@" not in email:
        return email
    parts = email.split("@")
    name = parts[0]
    domain = parts[1]
    if len(name) <= 1:
        return f"*@{domain}"
    return f"{name[0]}***@{domain}"

def mask_phone(phone: str) -> str:
    """Maschera un telefono: +39 347 *** ** 12"""
    if not phone:
        return phone
    # Strip spaces for uniform processing
    clean_phone = phone.replace(" ", "")
    if len(clean_phone) < 5:
        return phone
    # Show first 3 and last 2 digits
    return f"{clean_phone[:3]} *** *** {clean_phone[-2:]}"
