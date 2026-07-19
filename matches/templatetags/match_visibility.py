"""
Consumo del gate di visibilita' del risultato nei template.

Unico modo corretto di mostrare un punteggio in un template:

    {% load match_visibility %}
    {% if match|result_visible_to:request.user %}
        {{ match.home_score }}-{{ match.away_score }}
    {% else %}
        {{ UNVERIFIED_RESULT_LABEL }}   {# o il filtro `unverified_label` #}
    {% endif %}

La logica NON va replicata inline: sta tutta in
`matches.services.result_visibility`.
"""

from django import template

from ..services.result_visibility import (
    UNVERIFIED_RESULT_LABEL,
    UNVERIFIED_SCORE_PLACEHOLDER,
    can_see_result,
)

register = template.Library()


@register.filter
def result_visible_to(match, user=None):
    """True se questo spettatore puo' vedere il risultato di questa partita."""
    return can_see_result(match, user)


@register.simple_tag
def unverified_result_label():
    """Etichetta testuale del placeholder ('Risultato da verificare')."""
    return UNVERIFIED_RESULT_LABEL


@register.simple_tag
def unverified_score_placeholder():
    """Placeholder di un singolo numero ('—')."""
    return UNVERIFIED_SCORE_PLACEHOLDER
