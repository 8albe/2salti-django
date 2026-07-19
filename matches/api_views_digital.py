import json
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .models import Match, MatchReport, MatchReportAuditLog
from .services.schema import OCRSchemaValidator, SCHEMA_VERSION
from .services.jury_link_service import JuryLinkService

# Header (o query param) che veicola il token del link giuria per l'accesso
# no-account alle API digitali, in alternativa all'utente autenticato.
_JURY_TOKEN_HEADER = 'HTTP_X_JURY_TOKEN'


def _check_digital_report_permissions(user):
    """
    Check if the user has permission to handle digital reports.
    Allowed: staff with UPLOADER+ role, superusers, and referees.
    """
    if user.is_superuser:
        return True
    if user.staff_role in ['UPLOADER', 'REVIEWER', 'PUBLISHER', 'SUPERADMIN']:
        return True
    if user.role == 'referee':
        return True
    return False


def _get_jury_token(request):
    """Token giuria dall'header X-Jury-Token o, in fallback, dalla query string."""
    return request.META.get(_JURY_TOKEN_HEADER) or request.GET.get('jury_token')


def _valid_signature(signature):
    """Firma arbitro valida: nome e cognome (>=2 token) digitati al close."""
    sig = (signature or '').strip()
    parts = [p for p in sig.split() if p]
    return len(parts) >= 2 and len(sig) >= 3

@csrf_exempt
def api_digital_report_start(request):
    """
    POST /api/referti/digital/start
    Creates a new MatchReport in DRAFT state.
    Payload: {"match_id": 123, "initial_data": {...}}

    Accesso: utente autenticato con permessi digitali OPPURE (anonimo) token di
    link giuria ACTIVE valido per il match. L'accesso autenticato resta intatto.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        body = json.loads(request.body)
        match_id = body.get('match_id')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    if not match_id:
        return JsonResponse({'error': 'match_id is required'}, status=400)

    match = get_object_or_404(Match, id=match_id)

    # --- Autenticazione: utente autenticato (path esistente, intatto) o token giuria ---
    if request.user.is_authenticated:
        if not _check_digital_report_permissions(request.user):
            return JsonResponse({'error': 'Permission denied'}, status=403)
        actor = request.user
        jury_link = None
    else:
        jury_link = JuryLinkService.resolve(_get_jury_token(request), match=match)
        if not jury_link:
            return JsonResponse({'error': 'Authentication required'}, status=403)
        actor = None

    # Initialize JSON v2.0 structure if not provided
    initial_data = body.get('initial_data', {
        "metadata": {
            "version": SCHEMA_VERSION,
            "confidence": 1.0,
            "source": "digital_app",
            "timestamp": timezone.now().isoformat()
        },
        "match_info": {
            "home_team": match.home_team.name,
            "away_team": match.away_team.name,
            "date": match.match_date.isoformat(),
            "city": match.location
        },
        "scores": {
            "final_score": "0-0",
            "quarters": {}
        },
        "teams": {
            "home": {"players": []},
            "away": {"players": []}
        },
        "events": []
    })

    report = MatchReport.objects.create(
        match=match,
        uploader=actor,
        source_channel='DIGITAL',
        status=MatchReport.Status.DRAFT,
        raw_extracted_data=initial_data,
        normalized_data=initial_data
    )

    MatchReportAuditLog.objects.create(
        report=report,
        user=actor,
        action='create_digital',
        new_status=MatchReport.Status.DRAFT,
        reason=(
            'Inizio compilazione referto digitale via link giuria'
            if jury_link else 'Inizio compilazione referto digitale nativo'
        )
    )

    return JsonResponse({
        'id': report.id,
        'status': report.status,
        'data': report.raw_extracted_data
    }, status=201)

@csrf_exempt
def api_digital_report_update(request, report_id):
    """
    PUT /api/referti/digital/{id}
    Updates the draft data.

    Accesso: uploader/reviewer autenticato (path esistente, intatto) OPPURE
    token di link giuria ACTIVE valido per il match del referto.
    """
    if request.method != 'PUT':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    report = get_object_or_404(MatchReport, id=report_id, source_channel='DIGITAL')

    # --- Autenticazione: utente autenticato (path esistente) o token giuria ---
    if request.user.is_authenticated:
        # Security: Only uploader or admin/reviewer can update
        if report.uploader != request.user and not request.user.can_review:
            return JsonResponse({'error': 'Permission denied'}, status=403)
        jury_link = None
    else:
        jury_link = JuryLinkService.resolve(_get_jury_token(request), match=report.match)
        if not jury_link:
            return JsonResponse({'error': 'Authentication required'}, status=403)

    if report.status != MatchReport.Status.DRAFT:
        return JsonResponse({'error': f'Cannot update report in state {report.status}'}, status=400)

    try:
        body = json.loads(request.body)
        # We expect the full JSON v2.0 payload or a delta? 
        # For simplicity and robustness, we expect the full payload as per user's "Contratto Dati" instruction.
        data = body.get('data')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    if not data:
        return JsonResponse({'error': 'No data provided'}, status=400)

    # Partial structural validation (optional but recommended)
    # We save even if invalid during DRAFT, but we can return warnings
    report.raw_extracted_data = data
    report.normalized_data = data
    report.save()

    # Ogni azione VIA link giuria e' tracciata (user=None). L'update autenticata
    # resta senza audit come prima (comportamento invariato).
    if jury_link:
        MatchReportAuditLog.objects.create(
            report=report,
            user=None,
            action='update_digital',
            reason='Salvataggio bozza referto digitale via link giuria',
        )

    return JsonResponse({
        'id': report.id,
        'status': report.status,
        'message': 'Draft saved successfully'
    })

@csrf_exempt
def api_digital_report_close(request, report_id):
    """
    POST /api/referti/digital/{id}/close
    Validates and sends to review queue.
    Payload: {"signature": "Nome Cognome"} (firma arbitro obbligatoria).

    Accesso: uploader/reviewer autenticato (path esistente) OPPURE token di link
    giuria ACTIVE valido per il match. Il close finisce SEMPRE in NEEDS_REVIEW
    (nessun auto-publish). Il link ACTIVE del match va a CONSUMED solo su close
    riuscito, atomicamente col cambio stato del referto.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    report = get_object_or_404(MatchReport, id=report_id, source_channel='DIGITAL')

    # --- Autenticazione: utente autenticato (path esistente) o token giuria ---
    if request.user.is_authenticated:
        if report.uploader != request.user and not request.user.can_review:
            return JsonResponse({'error': 'Permission denied'}, status=403)
        actor = request.user
        jury_link = None
    else:
        jury_link = JuryLinkService.resolve(_get_jury_token(request), match=report.match)
        if not jury_link:
            return JsonResponse({'error': 'Authentication required'}, status=403)
        actor = None

    # Guardia di stato (idempotenza, fix 03d3860): un referto gia' fuori DRAFT
    # e' respinto senza rivalidare ne' transizionare, e senza consumare il link.
    if report.status != MatchReport.Status.DRAFT:
        return JsonResponse({'error': f'Cannot close report in state {report.status}'}, status=400)

    # 1. Firma arbitro obbligatoria (nome e cognome digitati). Campo di contratto
    #    -> 400 se mancante/non valida (distinto dal 422 di validazione schema).
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, AttributeError):
        body = {}
    signature = (body.get('signature') or '').strip()
    if not _valid_signature(signature):
        return JsonResponse(
            {'error': 'Firma arbitro (nome e cognome) obbligatoria'}, status=400
        )

    # 2. Structural Validation
    success, error_msg = OCRSchemaValidator.validate(report.raw_extracted_data)
    if not success:
        return JsonResponse({
            'error': 'Validation failed',
            'details': error_msg
        }, status=422)

    # 3. Transizione di stato + firma + consume link, atomici.
    old_status = report.status
    with transaction.atomic():
        report.status = MatchReport.Status.NEEDS_REVIEW
        report.referee_signature = signature
        report.save(update_fields=['status', 'referee_signature', 'updated_at'])

        MatchReportAuditLog.objects.create(
            report=report,
            user=actor,
            action='close_digital',
            old_status=old_status,
            new_status=MatchReport.Status.NEEDS_REVIEW,
            reason=(
                'Chiusura referto digitale via link giuria e invio in review queue'
                if jury_link else 'Chiusura referto digitale e invio in review queue'
            ),
            after={'referee_signature': signature},
        )

        # Il link muore alla chiusura del referto: consuma il link usato per il
        # close (jury) o, per un close autenticato, l'eventuale link ACTIVE
        # ancora pendente sul match.
        link_to_consume = jury_link or JuryLinkService.active_for_match(report.match)
        if link_to_consume:
            JuryLinkService.consume(link_to_consume, report=report)

    return JsonResponse({
        'id': report.id,
        'status': report.status,
        'message': 'Report submitted for review'
    })
