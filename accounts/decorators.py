"""Decorator di gating premium — ORTOGONALI all'RBAC.

Separati da ``management/permissions.py`` (RBAC): questi non toccano ruoli né
membership, gattano solo sull'entitlement premium (``User.is_premium`` /
``Society.is_club_pro``, fonti-di-verità uniche). Stile ``onboarding_required``.

Da comporre DOPO ``login_required`` nella catena (login prima, premium poi), così
l'utente anonimo riceve il redirect al login (CTA accesso, coerente con a573022)
e non un 403 grezzo.
"""
from functools import wraps

from django.http import JsonResponse
from django.shortcuts import redirect


def premium_required(view_func):
    """Richiede ``request.user.is_premium``.

    Freemium → ``JsonResponse({'error': 'premium_required'}, status=403)`` così il
    client (barra AI) può mostrare un CTA di upgrade. Utente anonimo → redirect al
    login (di norma già gestito da ``login_required`` a monte).
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect('login')
        if not user.is_premium:
            return JsonResponse(
                {
                    'error': 'premium_required',
                    'message': 'Questa funzione è riservata al piano Premium.',
                },
                status=403,
            )
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def club_pro_required(view_func):
    """Richiede che la società di contesto sia Club Pro (tier o comped).

    CREATO ma NON applicato in pilota (Zero9 sarà comped → gate inerte). Risolve la
    società via ``management.permissions.get_society_context`` (sola lettura; import
    lazy per non creare dipendenza di modulo accounts→management).
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect('login')
        from management.permissions import get_society_context
        society = get_society_context(request)
        if society is None or not society.is_club_pro:
            return JsonResponse(
                {
                    'error': 'club_pro_required',
                    'message': 'Questa funzione è riservata alle società Club Pro.',
                },
                status=403,
            )
        return view_func(request, *args, **kwargs)
    return _wrapped_view
