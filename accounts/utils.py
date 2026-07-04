from functools import wraps
from django.shortcuts import redirect

def onboarding_required(view_func):
    """
    Decorator per forzare l'utente a completare i passaggi di onboarding (Identità -> Pagamento)
    prima di accedere a determinate viste (Setup, Team Access, ecc.).
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect('login')
        
        # 1. Verifica Identità
        if user.identity_status != 'VERIFIED':
            # Se NON siamo già nella vista di verifica, redirect
            if request.resolver_match.url_name != 'verify_identity':
                return redirect('verify_identity')
        
        # 2. Verifica Pagamento onboarding (asse separato dal piano premium)
        elif not user.onboarding_payment_done:
            # Se NON siamo nella vista di pagamento (e non siamo in quella di identità), redirect
            if request.resolver_match.url_name not in ['process_payment', 'verify_identity']:
                return redirect('process_payment')
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view
