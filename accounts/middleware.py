from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin

class OnboardingMiddleware(MiddlewareMixin):
    """
    Forza l'utente a completare il funnel di onboarding (Identity -> Setup -> Membership).
    Redirige alle viste corrette in base a User.onboarding_state.
    """
    def process_request(self, request):
        if not request.user.is_authenticated:
            return None

        # Lista di URL permessi durante l'onboarding per evitare loop
        allowed_urls = [
            reverse('verify_identity'),
            reverse('process_payment'),
            reverse('setup_wizard'),
            reverse('onboarding_membership'),
            reverse('claim_profile'),
            reverse('team_access'),
            reverse('create_society'),
	    reverse('choose_society'),
            reverse('logout'),
            # Aggiungere altri se necessario (es: static, media, api di ricerca)
        ]
        
        # AJAX e API non dovrebbero essere redirette dal middleware (gestite a livello di vista)
        # §10.13: /accounts/api/ è una API AJAX (teams-by-league, search-athlete,
        # search-profile-claim) usata DENTRO il funnel onboarding; va esentata dal
        # redirect anche quando il client non manda l'header XMLHttpRequest.
        # Prefisso stretto e specifico, voce additiva e minima.
        if (request.path.startswith('/api/')
                or request.path.startswith('/accounts/api/')
                or request.headers.get('x-requested-with') == 'XMLHttpRequest'):
            return None

        # Se l'utente è in un URL permesso o è uno staff/superadmin, non fare nulla
        if request.path in allowed_urls or request.user.is_staff or request.user.is_superuser:
            return None

        state = request.user.onboarding_state

        if state == 'IDENTITY_PENDING':
            return redirect('verify_identity')
        elif state == 'SETUP_PENDING':
            return redirect('setup_wizard')
        elif state == 'MEMBERSHIP_PENDING':
            return redirect('onboarding_membership')
            
        return None
