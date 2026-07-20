"""
API a livello di referto (BLUEPRINT §11).

Per ora il solo endpoint di stato, che regge il polling del client dopo un
upload asincrono (Macro 22). `results` e `validate` del blueprint restano da
fare e troveranno casa qui.
"""
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from management.permissions import get_membership_context

from .models import MatchReport
from .api_views_digital import _check_digital_report_permissions

from .status_presentation import PIPELINE_STATUSES

# Stati in cui il referto e' ancora in mano alla pipeline OCR: finche' lo
# stato e' uno di questi, il client continua a fare polling.
# La lista NON si scrive qui: viverne una copia locale significa che un nuovo
# stato transitorio verrebbe dichiarato `is_final: true` e il client smetterebbe
# di aggiornare la pagina su un referto ancora in lavorazione.
NON_FINAL_STATES = PIPELINE_STATUSES


def _can_read_report_status(request, report):
    """
    Chi puo' leggere lo stato di un referto: chi lo ha caricato, lo staff che
    lo lavora, e i vertici delle due squadre coinvolte. Stesso perimetro della
    upload view, piu' l'uploader. Nessun accesso anonimo: un referto non
    pubblicato non e' informazione pubblica.
    """
    user = request.user

    if user.is_superuser:
        return True
    if report.uploader_id == user.id:
        return True
    if _check_digital_report_permissions(user):  # staff_role UPLOADER+ o referee
        return True

    match = report.match
    if match:
        for team in (match.home_team, match.away_team):
            membership = get_membership_context(request, team=team)
            if membership and membership.role in ['PRESIDENT', 'HEAD_COACH']:
                return True
    return False


@login_required
def api_report_status(request, report_id):
    """
    GET /api/referti/{id}/status — stato di workflow del referto.

    Payload deliberatamente minimo: niente `validation_notes` ne' dettagli di
    blocco, che sono materia della review page, non del polling.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    report = get_object_or_404(MatchReport, id=report_id)

    if not _can_read_report_status(request, report):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    return JsonResponse({
        'report_id': report.id,
        'status': report.status,
        'status_display': report.get_status_display(),
        'is_final': report.status not in NON_FINAL_STATES,
        'queued_at': report.ocr_queued_at.isoformat() if report.ocr_queued_at else None,
        'started_at': report.ocr_started_at.isoformat() if report.ocr_started_at else None,
        'attempts': report.ocr_attempts,
        'updated_at': report.updated_at.isoformat() if report.updated_at else None,
    })
