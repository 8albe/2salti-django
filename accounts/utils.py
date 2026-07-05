from functools import wraps
from django.shortcuts import redirect

def onboarding_required(view_func):
    """
    Decorator per forzare l'utente a completare i passaggi di onboarding (Identità)
    prima di accedere a determinate viste (Setup, Team Access, ecc.).
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect('login')

        # Verifica Identità (pagamento: differito a Macro 10 pagamenti reali)
        if user.identity_status != 'VERIFIED':
            # Se NON siamo già nella vista di verifica, redirect
            if request.resolver_match.url_name != 'verify_identity':
                return redirect('verify_identity')

        return view_func(request, *args, **kwargs)
    return _wrapped_view
