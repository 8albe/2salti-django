"""
Gate unico per la visibilita' PUBBLICA del risultato di una partita.

Decisione di prodotto ratificata il 2026-07-19 (BLUEPRINT cap. 14): la pagina
pubblica non mostra il risultato di una partita i cui dati non sono verificati.
Discende dal Principio del Dato Certo (BLUEPRINT cap. 1): se un dato non e'
certo il sistema lo dichiara, non lo mostra come se lo fosse.

Semantica (UNA sola, da non duplicare altrove):

    il risultato e' pubblico  <=>  is_data_verified=True
                                   OPPURE almeno un report in stato PUBLISHED

Le due strade sono entrambe legittime e sono le uniche due: la validazione
umana diretta sul Match e il workflow di pubblicazione del referto. La seconda
e' lo stesso criterio gia' usato da `StandingsService` per le classifiche, cosi'
il gate pubblico resta allineato a quello delle classifiche invece di
introdurre un terzo concetto di "verificato".

Il gate vale SOLO sul pubblico: staff e superuser continuano a vedere il
punteggio, perche' vederlo e' esattamente cio' che serve per verificarlo.

Non nasconde MAI la partita: squadre, data, luogo e competizione restano
pubblici. Il match esiste, e' il risultato a non essere ancora certo.
"""

from django.db.models import Q

# Testo mostrato al posto del punteggio finale quando il risultato non e' certo.
UNVERIFIED_RESULT_LABEL = "Risultato da verificare"

# Testo mostrato al posto di un singolo numero (parziali, punteggi in riga).
UNVERIFIED_SCORE_PLACEHOLDER = "—"

# Stato del referto che rende pubblico il risultato. Stringa e non
# `MatchReport.Status.PUBLISHED` per tenere questo modulo privo di import di
# modelli: cosi' e' importabile da `matches.models` senza ciclo.
_PUBLISHED = "PUBLISHED"


def result_public_q(prefix: str = "") -> Q:
    """
    Il gate in forma di `Q`, per filtrare queryset.

    `prefix` permette di attraversare una relazione: per filtrare `MatchEvent`
    si usa `result_public_q("match__")`.

    Attenzione: il ramo sui report attraversa una relazione to-many, quindi il
    queryset che consuma questa `Q` deve chiamare `.distinct()`.
    """
    return (
        Q(**{f"{prefix}is_data_verified": True})
        | Q(**{f"{prefix}reports__status": _PUBLISHED})
    )


def is_result_public(match) -> bool:
    """Il gate in forma booleana su una singola istanza di Match."""
    if match is None:
        return False
    if match.is_data_verified:
        return True
    return match.reports.filter(status=_PUBLISHED).exists()


def can_see_result(match, user=None) -> bool:
    """
    Il gate effettivo per un dato spettatore.

    Pubblico: solo se il risultato e' pubblico.
    Staff/superuser: sempre, e' il loro strumento di lavoro.
    """
    if is_result_public(match):
        return True
    return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))
