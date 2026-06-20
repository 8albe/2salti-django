from functools import wraps
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from .models import Membership

def get_society_context(request):
    """
    Risolve la società corrente con fallback alla membership se non presente nel middleware.
    """
    if hasattr(request, 'current_society') and request.current_society:
        return request.current_society
    
    if request.user.is_authenticated:
        # Fallback alla prima membership attiva
        membership = Membership.objects.filter(user=request.user, is_active=True).first()
        if membership:
            return membership.society
        
        # Fallback ai profili (Presidente, Coach, ecc.)
        if hasattr(request.user, 'president_profile'):
            return request.user.president_profile.managed_society
            
    return None

def get_membership_context(request, society=None, team=None):
    """
    Risolve la membership dell'utente per un determinato contesto.
    Gestisce correttamente i ruoli di società (es: PRESIDENT) quando si accede a un team.
    """
    if not request.user.is_authenticated:
        return None
        
    if team:
        from django.db.models import Q
        # Cerca membership specifica al team O alla società (ruoli globali)
        return Membership.objects.filter(
            Q(team=team) | Q(society=team.society, team__isnull=True),
            user=request.user, 
            is_active=True
        ).first() # In generale un utente ha un solo ruolo per team/società
        
    filters = {'user': request.user, 'is_active': True}
    if society:
        filters['society'] = society
        
    return Membership.objects.filter(**filters).first()

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

    roles = list(qs.values_list('role', flat=True))

    # Fallback presidente de-vincolato (§10.10): dal Macro 7 il presidente non
    # possiede più una Membership PRESIDENT stagionale — il suo ruolo deriva da
    # president_profile.managed_society. Se la società gestita coincide con quella
    # in scope (o lo scope è globale, society=None) si inietta 'PRESIDENT' così che
    # role_required([... 'PRESIDENT' ...]) non lo escluda. getattr a doppio salto:
    # il reverse OneToOne assente solleva RelatedObjectDoesNotExist (sottoclasse di
    # AttributeError), quindi degrada a None senza eccezione (stesso idioma di hasattr).
    if 'PRESIDENT' not in roles:
        managed = getattr(getattr(user, 'president_profile', None), 'managed_society', None)
        if managed is not None and (society is None or managed == society):
            roles.append('PRESIDENT')

    return roles

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
