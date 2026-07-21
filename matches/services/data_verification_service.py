"""Data verification seam — unico punto da cui si scrive ``Match.is_data_verified``.

Perché esiste (2026-07-21, fetta B1). ``is_data_verified`` è il flag che, insieme
all'esistenza di un referto ``PUBLISHED``, decide se il risultato di una partita è
**visibile al pubblico** (``matches/services/result_visibility.py``, BLUEPRINT §14).
Fino al 2026-07-19 era un campo morto; da quando è vivo, ogni sua scrittura è
un'affermazione forte — "questo punteggio è vero" — fatta su un dominio in cui il
100% della popolazione a DB è risultato sbagliato almeno una volta
(``docs/syllabus/8_ocr_affidabilita.md`` §8.5(d)).

Un'affermazione del genere non può essere un ``match.is_data_verified = True`` sparso
nel codice o incollato in una shell: deve lasciare **chi**, **quando** e soprattutto
**perché**. Da qui la stessa forma del seam degli entitlement
(``core/services/entitlement_service.py``): funzione unica, idempotente, che scrive
una riga ``AuditLog``.

Differenza deliberata rispetto al seam entitlement: qui ``reason`` è **obbligatoria**
e non vuota. Un tier si cambia per ragioni contrattuali ovvie; una verifica di dato
senza il motivo registrato — su quale fonte, contro quale cartaceo — non è
verificabile a posteriori, ed è esattamente ciò che serve fra sei mesi.
"""
from management.utils import log_action

#: Nome dell'azione scritta in ``management_auditlog``.
AUDIT_ACTION = 'MATCH_DATA_VERIFIED_SET'


def set_data_verified(match, value, user, reason, *, request=None):
    """Imposta ``match.is_data_verified``. Idempotente. Logga ``MATCH_DATA_VERIFIED_SET``.

    Args:
        match: il ``Match`` da marcare.
        value: valore booleano da impostare (``True`` = dato verificato).
        user: chi compie l'atto. Può essere ``None`` solo per operazioni di
            sistema (data migration, comandi), e in quel caso ``reason`` deve
            dirlo esplicitamente.
        reason: motivo non vuoto. Su cosa si basa la verifica (es. "collazione
            sul cartaceo originale, doppia lettura 19/07 e 20/07").
        request: opzionale, per registrare l'IP nell'audit.

    Returns:
        bool: ``True`` se il valore è cambiato, ``False`` se era già quello
        (no-op silenzioso, nessuna riga di audit).

    Raises:
        ValueError: se ``value`` non è un bool o se ``reason`` è vuota.
    """
    if not isinstance(value, bool):
        raise ValueError("set_data_verified: 'value' deve essere un booleano.")
    if not reason or not str(reason).strip():
        raise ValueError(
            "set_data_verified: 'reason' è obbligatoria e non può essere vuota — "
            "una verifica senza motivo registrato non è verificabile a posteriori."
        )

    old = match.is_data_verified
    if old == value:
        return False

    match.is_data_verified = value
    match.save(update_fields=['is_data_verified'])

    society = getattr(getattr(match, 'home_team', None), 'society', None)
    log_action(
        user, society, AUDIT_ACTION, target=match,
        details={
            'from': old,
            'to': value,
            'reason': str(reason).strip(),
            'match_id': match.pk,
        },
        request=request,
    )
    return True
