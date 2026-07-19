import json
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import Match, MatchReport, MatchReportAuditLog
from .services.schema import OCRSchemaValidator, SCHEMA_VERSION

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

@csrf_exempt
@login_required
def api_digital_report_start(request):
    """
    POST /api/referti/digital/start
    Creates a new MatchReport in DRAFT state.
    Payload: {"match_id": 123, "initial_data": {...}}
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    if not _check_digital_report_permissions(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    try:
        body = json.loads(request.body)
        match_id = body.get('match_id')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    if not match_id:
        return JsonResponse({'error': 'match_id is required'}, status=400)

    match = get_object_or_404(Match, id=match_id)
    
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
        uploader=request.user,
        source_channel='DIGITAL',
        status=MatchReport.Status.DRAFT,
        raw_extracted_data=initial_data,
        normalized_data=initial_data
    )

    MatchReportAuditLog.objects.create(
        report=report,
        user=request.user,
        action='create_digital',
        new_status=MatchReport.Status.DRAFT,
        reason='Inizio compilazione referto digitale nativo'
    )

    return JsonResponse({
        'id': report.id,
        'status': report.status,
        'data': report.raw_extracted_data
    }, status=201)

@csrf_exempt
@login_required
def api_digital_report_update(request, report_id):
    """
    PUT /api/referti/digital/{id}
    Updates the draft data.
    """
    if request.method != 'PUT':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    report = get_object_or_404(MatchReport, id=report_id, source_channel='DIGITAL')

    # Security: Only uploader or admin/reviewer can update
    if report.uploader != request.user and not request.user.can_review:
        return JsonResponse({'error': 'Permission denied'}, status=403)

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

    return JsonResponse({
        'id': report.id,
        'status': report.status,
        'message': 'Draft saved successfully'
    })

@csrf_exempt
@login_required
def api_digital_report_close(request, report_id):
    """
    POST /api/referti/digital/{id}/close
    Validates and sends to review queue.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    report = get_object_or_404(MatchReport, id=report_id, source_channel='DIGITAL')

    if report.uploader != request.user and not request.user.can_review:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    if report.status != MatchReport.Status.DRAFT:
        return JsonResponse({'error': f'Cannot close report in state {report.status}'}, status=400)

    # 1. Structural Validation
    success, error_msg = OCRSchemaValidator.validate(report.raw_extracted_data)
    if not success:
        return JsonResponse({
            'error': 'Validation failed',
            'details': error_msg
        }, status=422)

    # 2. State transition
    old_status = report.status
    report.status = MatchReport.Status.NEEDS_REVIEW
    report.save()

    MatchReportAuditLog.objects.create(
        report=report,
        user=request.user,
        action='close_digital',
        old_status=old_status,
        new_status=MatchReport.Status.NEEDS_REVIEW,
        reason='Chiusura referto digitale e invio in review queue'
    )

    return JsonResponse({
        'id': report.id,
        'status': report.status,
        'message': 'Report submitted for review'
    })
