from django import template
from django.utils.safestring import mark_safe
import json

register = template.Library()

@register.filter
def clean_team_name(value):
    """Rimuove 'Prima Squadra' dal nome del team"""
    if value:
        return value.replace(" Prima Squadra", "").replace("Prima Squadra", "").strip()
    return value

@register.simple_tag
def render_json_ld(schema_dict):
    """Renderizza un blocco script JSON-LD in modo sicuro"""
    if not schema_dict:
        return ""
    
    # Assicurati che sia una lista se passati più schemi
    if not isinstance(schema_dict, list):
        schema_dict = [schema_dict]
        
    scripts = ""
    for sd in schema_dict:
        json_data = json.dumps(sd, ensure_ascii=False)
        scripts += f'<script type="application/ld+json">{json_data}</script>\n'
        
    return mark_safe(scripts)
