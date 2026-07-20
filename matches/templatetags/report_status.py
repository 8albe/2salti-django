"""
Consumo nei template della presentazione unica degli stati referto.

Unico modo corretto di colorare un badge di stato:

    {% load report_status %}
    <span class="... {{ report.status|status_classes:'dark' }}">
        {{ report.get_status_display }}
    </span>

Mai una catena `{% if report.status == '...' %}` inline: si rompe in silenzio
quando nasce uno stato nuovo. La mappa sta in
`matches.status_presentation` e i test la verificano totale su `Status.choices`.

Il filtro accetta sia la stringa dello stato sia l'istanza di `MatchReport`,
perche' i template a volte iterano su oggetti e a volte su codici (es. il
funnel di `staff_dashboard.html`, che cicla sulle chiavi di un dict).
"""
from django import template

from ..models import MatchReport
from ..status_presentation import PALETTES, classes_for

register = template.Library()

_LABELS = dict(MatchReport.Status.choices)


@register.filter
def status_classes(value, theme='dark'):
    """
    Classi CSS del badge per questo stato nel tema richiesto.

    Uno stato sconosciuto (dato sporco, non un valore di `Status`) degrada al
    tono neutro invece di far esplodere la pagina: il badge e' decorativo, non
    vale una 500. Gli stati *dichiarati* ma non mappati sono invece intercettati
    dai test, non a runtime.
    """
    status = getattr(value, 'status', value)
    try:
        return classes_for(status, theme)
    except KeyError:
        return PALETTES.get(theme, PALETTES['dark'])['neutral']


@register.filter
def status_label(value):
    """
    Etichetta italiana di uno stato a partire dal *codice*.

    Serve dove il template cicla su codici e non su istanze — il funnel di
    `staff_dashboard.html` itera le chiavi di un dict di conteggi — e quindi
    non puo' chiamare `get_status_display`. Stampare il codice grezzo, come si
    faceva prima, mostrava allo staff 'NEEDS_REVIEW' invece di
    'Revisione Tecnica Necessaria'.
    """
    status = getattr(value, 'status', value)
    return _LABELS.get(status, status)
