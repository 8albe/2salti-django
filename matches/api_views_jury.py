"""
Endpoint di emissione/revoca del link giuria e landing pubblica /r/{token}
(Macro 14). Neutralita' di canale: la risposta di emissione fornisce l'URL, non
genera QR ne' presuppone mail. Nessuna UI in questo giro.
"""
import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required

from .models import Match, MatchJuryLink, MatchReport
from .services.jury_link_service import JuryLinkService
from .api_views_digital import _check_digital_report_permissions


def _jury_link_url(request, link):
    """URL assoluto della landing /r/{token} (neutrale rispetto al canale)."""
    return request.build_absolute_uri(f'/r/{link.token}/')


@csrf_exempt
@login_required
def api_jury_link_issue(request, match_id):
    """
    POST /api/matches/{id}/jury-link/
    Emette un link giuria ACTIVE per il match (revoca il precedente ACTIVE).
    Gate: staff digitale/admin (stesso gate di start/close digitali). Il RBAC
    non e' society-scoped: staff_role e' globale (vedi recon Macro 14).
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    if not _check_digital_report_permissions(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    match = get_object_or_404(Match, id=match_id)
    link = JuryLinkService.issue(match, created_by=request.user)
    # L'emissione precede il referto: MatchReportAuditLog richiede un report FK,
    # quindi la riga MatchJuryLink stessa (created_by + created_at) e' il suo
    # audit trail. Le azioni VIA link (start/update/close) sono invece loggate
    # in MatchReportAuditLog con user=None (vedi api_views_digital).

    return JsonResponse({
        'match_id': match.id,
        'url': _jury_link_url(request, link),
        'token': link.token,
        'status': link.status,
        'expires_at': link.expires_at.isoformat(),
    }, status=201)


@csrf_exempt
@login_required
def api_jury_link_revoke(request, match_id):
    """
    POST /api/matches/{id}/jury-link/revoke/
    Revoca l'eventuale link ACTIVE del match.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    if not _check_digital_report_permissions(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    match = get_object_or_404(Match, id=match_id)
    revoked = JuryLinkService.revoke(match)

    return JsonResponse({
        'match_id': match.id,
        'revoked': revoked,
    })


def jury_link_landing(request, token):
    """
    GET /r/{token}
    Risoluzione minima del link (nessuna UI in questo giro):
      - token valido (ACTIVE + non scaduto) -> 200 con l'identita' di match/referto
      - token scaduto o gia' consumato/revocato -> 410 Gone
      - token inesistente -> 404
    """
    try:
        link = MatchJuryLink.objects.select_related(
            'match', 'match__home_team__society', 'match__away_team__society'
        ).get(token=token)
    except MatchJuryLink.DoesNotExist:
        return JsonResponse({'error': 'Link non trovato'}, status=404)

    # ACTIVE ma scaduto per tempo -> degrada a EXPIRED (lazy) e trattalo come gone.
    if link.status == MatchJuryLink.Status.ACTIVE and link.is_expired_by_time:
        link.status = MatchJuryLink.Status.EXPIRED
        link.save(update_fields=['status'])

    if link.status != MatchJuryLink.Status.ACTIVE:
        return JsonResponse({
            'error': 'Link non più valido',
            'status': link.status,
        }, status=410)

    match = link.match
    # Eventuale bozza digitale gia' aperta per questo match (riprende la compilazione).
    draft = MatchReport.objects.filter(
        match=match, source_channel='DIGITAL', status=MatchReport.Status.DRAFT
    ).order_by('-created_at').first()

    return JsonResponse({
        'status': link.status,
        'match': {
            'id': match.id,
            'home_team': match.home_team.name,
            'away_team': match.away_team.name,
            'date': match.match_date.isoformat(),
            'city': match.location,
        },
        'draft_report_id': draft.id if draft else None,
        'expires_at': link.expires_at.isoformat(),
    })
