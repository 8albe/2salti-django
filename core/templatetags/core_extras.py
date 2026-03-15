from django import template

register = template.Library()

@register.filter
def clean_team_name(value):
    """Rimuove 'Prima Squadra' dal nome del team"""
    if value:
        return value.replace(" Prima Squadra", "").replace("Prima Squadra", "").strip()
    return value
