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
