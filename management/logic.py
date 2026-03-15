from datetime import timedelta
from django.utils import timezone
from .models import TrainingOccurrence, Training

def generate_occurrences(training):
    """
    Genera le occorrenze per un allenamento in base alla sua regola di ricorrenza.
    """
    if not training.is_recurring or not training.recurrence_rule:
        # Se non è ricorrente, creiamo solo l'occorrenza base se non esiste
        TrainingOccurrence.objects.get_or_create(
            training=training,
            start_time=training.start_time,
            end_time=training.end_time
        )
        return

    rule = training.recurrence_rule
    freq = rule.get('freq', 'WEEKLY')
    until = rule.get('until')
    days = rule.get('days', []) # [0, 1, 2, 3, 4, 5, 6] -> Lun-Dom
    
    if not until:
        # Default: 3 mesi di occorrenze se non specificato
        until_dt = training.start_time + timedelta(days=90)
    else:
        from django.utils.dateparse import parse_datetime
        until_dt = parse_datetime(until)
        if not until_dt:
             # Fallback simple date parse YYYY-MM-DD
             from datetime import datetime
             until_dt = timezone.make_aware(datetime.strptime(until, '%Y-%m-%d'))

    current_start = training.start_time
    duration = training.end_time - training.start_time
    
    occurrences = []
    
    # Loop fino alla data di fine
    while current_start <= until_dt:
        # Se settimanale, controlla se il giorno della settimana è incluso
        if freq == 'WEEKLY':
            if current_start.weekday() in days:
                occurrences.append(
                    TrainingOccurrence(
                        training=training,
                        start_time=current_start,
                        end_time=current_start + duration
                    )
                )
        elif freq == 'DAILY':
            occurrences.append(
                TrainingOccurrence(
                    training=training,
                    start_time=current_start,
                    end_time=current_start + duration
                )
            )
        
        # Incrementa di un giorno
        current_start += timedelta(days=1)
        
        # Safety break (Max 365 occorrenze per volta)
        if len(occurrences) > 365:
            break
            
    # Bulk create
    TrainingOccurrence.objects.bulk_create(occurrences)
