from django.utils.deprecation import MiddlewareMixin
from .models import Membership
from core.models import Society

class MembershipMiddleware(MiddlewareMixin):
    """
    Middleware per gestire il contesto della Società corrente e della Membership dell'utente.
    """
    def process_view(self, request, view_func, view_args, view_kwargs):
        request.current_society = None
        request.user_membership = None
        
        # Identifica la società corrente dallo slug nell'URL
        society_slug = view_kwargs.get('society_slug') or view_kwargs.get('slug')
        if society_slug:
            # Semplificazione: se lo slug corrisponde a una società, la impostiamo come corrente
            try:
                request.current_society = Society.objects.get(slug=society_slug)
            except Society.DoesNotExist:
                pass
        
        # Se abbiamo una società e l'utente è autenticato, recuperiamo la membership
        if request.user.is_authenticated and request.current_society:
            request.user_membership = Membership.objects.filter(
                user=request.user,
                society=request.current_society,
                is_active=True
            ).first()
            
        return None
