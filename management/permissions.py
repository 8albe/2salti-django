from functools import wraps
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from .models import Membership

def get_user_roles(user, society=None, team=None):
    """
    Ritorna i ruoli dell'utente in un determinato contesto.
    """
    filters = {'user': user, 'is_active': True}
    if society:
        filters['society'] = society
    if team:
        filters['team'] = team
    
    return list(user.memberships.filter(**filters).values_list('role', flat=True))

def has_role(user, roles, society=None, team=None):
    """
    Verifica se l'utente ha almeno uno dei ruoli specificati.
    """
    if user.is_superuser:
        return True
        
    user_roles = get_roles(user, society, team)
    return any(role in roles for role in user_roles)

def get_roles(user, society=None, team=None):
    """Helper internale per recuperare i ruoli"""
    if not user.is_authenticated:
        return []
        
    qs = Membership.objects.filter(user=user, is_active=True)
    if society:
        qs = qs.filter(society=society)
    if team:
        # Se controlliamo il team, includiamo anche i ruoli a livello di società (es: Presidente)
        from django.db.models import Q
        qs = qs.filter(Q(team=team) | Q(team__isnull=True))
    
    return list(qs.values_list('role', flat=True))

# Decoratori per Views

def role_required(roles, society_slug_field=None, team_slug_field=None):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            society = None
            team = None
            
            # Se vengono passati slug nelle URL, recuperiamo gli oggetti per il controllo
            if society_slug_field and society_slug_field in kwargs:
                from core.models import Society
                society = get_object_or_404(Society, slug=kwargs[society_slug_field])
            
            if team_slug_field and team_slug_field in kwargs:
                from core.models import Team
                team = get_object_or_404(Team, slug=kwargs[team_slug_field])
                if team and not society:
                    society = team.society

            if not has_role(request.user, roles, society=society, team=team):
                raise PermissionDenied
            
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator
