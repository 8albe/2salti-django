import logging
from typing import Tuple
from matches.models import MatchReport, MatchEvent
from .converters import MatchDataConverter
from .data_verification_service import set_data_verified
from .schema import OCRSchemaValidator, LEVEL_FULL, LEVEL_SCORE_ONLY
from .standings_service import StandingsService
from django.db import transaction
from django.utils import timezone
from management.models import AuditLog

logger = logging.getLogger(__name__)

# --- Guardrail "dato verificato" (prerequisito 1, 2026-07-21) ----------------
#
# `Match` e' una PROIEZIONE del referto (opzione A, ratificata il 2026-07-21):
# l'unico scrittore legittimo dei punteggi e' `publish_report`. Esiste pero' una
# popolazione di Match i cui punteggi sono stati verificati a mano contro il
# referto cartaceo (`is_data_verified=True`, scritto dal seam
# `data_verification_service.set_data_verified`) mentre il `normalized_data` del
# referto collegato e' ancora quello sbagliato dell'estrazione OCR.
#
# Su quei match una pubblicazione produce due danni, e il secondo e' il peggiore:
#   1. sovrascrive i valori corretti con quelli sbagliati del referto;
#   2. lascia `is_data_verified=True`, quindi il dato sbagliato resta
#      pubblicamente visibile *come verificato da un umano* — un'affermazione
#      che nessuno ha piu' fatto.
#
# Il guardrail blocca solo le pubblicazioni DISTRUTTIVE: se i valori proiettati
# coincidono con quelli gia' sul Match non c'e' nulla da difendere e il publish
# passa senza attriti.

#: Azione scritta in `MatchReportAuditLog` quando un publish forzato sovrascrive
#: i dati di un Match verificato a mano.
FORCED_OVERWRITE_AUDIT_ACTION = 'publish_force_verified_override'


def _as_int(value):
    """Forma intera confrontabile, o ``None`` se il valore non e' un numero.

    Serve a non trattare come divergenza una differenza di sola
    rappresentazione (``"6"`` contro ``6``): la proiezione riscriverebbe la
    forma, non il significato, e bloccare su questo sarebbe un falso positivo.
    """
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _normalize_quarters(quarters):
    """Parziali in forma confrontabile: chiavi stringa, valori coppie di int."""
    if not isinstance(quarters, dict):
        return {}
    normalized = {}
    for key, value in quarters.items():
        if isinstance(value, (list, tuple)) and len(value) == 2:
            normalized[str(key)] = (_as_int(value[0]), _as_int(value[1]))
        else:
            # Forma inattesa: confrontata com'e', mai silenziata.
            normalized[str(key)] = value
    return normalized


def detect_verified_projection_conflict(match, match_params):
    """Divergenza fra i dati verificati a mano sul Match e quelli da proiettare.

    Args:
        match: il ``Match`` bersaglio della proiezione (puo' essere ``None``).
        match_params: output di ``MatchDataConverter.get_match_scores``.

    Returns:
        dict | None: ``None`` se non c'e' conflitto — perche' il match non
        esiste, perche' non e' verificato, o perche' i valori coincidono.
        Altrimenti un dict con i campi divergenti e i valori prima/dopo, pronto
        per l'audit.
    """
    if match is None or not getattr(match, 'is_data_verified', False):
        return None

    diverging = []

    current_final = (_as_int(match.home_score), _as_int(match.away_score))
    projected_final = (_as_int(match_params.get('home_score')),
                       _as_int(match_params.get('away_score')))
    if current_final != projected_final:
        diverging.append('final_score')

    current_quarters = _normalize_quarters(match.quarter_scores)
    projected_quarters = _normalize_quarters(match_params.get('quarter_scores'))
    if current_quarters != projected_quarters:
        diverging.append('quarter_scores')

    if not diverging:
        return None

    return {
        'diverging_fields': diverging,
        'before': {
            'home_score': match.home_score,
            'away_score': match.away_score,
            'quarter_scores': match.quarter_scores,
            'is_data_verified': True,
        },
        'after': {
            'home_score': match_params.get('home_score'),
            'away_score': match_params.get('away_score'),
            'quarter_scores': match_params.get('quarter_scores'),
            'is_data_verified': False,
        },
    }


def _conflict_summary(conflict):
    """Sintesi leggibile della divergenza, per messaggi e log."""
    before, after = conflict['before'], conflict['after']
    parts = []
    if 'final_score' in conflict['diverging_fields']:
        parts.append(
            f"finale {before['home_score']}-{before['away_score']} "
            f"-> {after['home_score']}-{after['away_score']}"
        )
    if 'quarter_scores' in conflict['diverging_fields']:
        parts.append(f"parziali {before['quarter_scores']} -> {after['quarter_scores']}")
    return "; ".join(parts)

class PublishingService:
    """
    Servizio per la pubblicazione dei dati strutturati estratti dall'OCR.
    MVP+: Aggiorna Match e crea MatchEvent se riconciliati.
    Hardened v2: semantic guardrails before publish.
    """

    @staticmethod
    def publish_report(report: MatchReport, user=None, force: bool = False, reason: str = '',
                       level: str = LEVEL_FULL) -> Tuple[bool, str]:
        """
        Trasferisce i dati dal report (normalized_data) al record Match e crea eventi.
        Transactional, Idempotent, and Safe on Re-publish.

        `level` (Opzione A):
          - LEVEL_FULL (default): comportamento storico, INVARIATO. Crea gli
            eventi e valuta l'abort zero-eventi (Policy A strict).
          - LEVEL_SCORE_ONLY: proietta punteggio e parziali, NON crea eventi e
            cancella quelli esistenti (il referto dichiara "eventi non
            disponibili"); l'abort zero-eventi NON viene valutato. La proiezione
            dei punteggi, il guardrail dato-verificato, il supersede e il rebuild
            della classifica sono IDENTICI ai due livelli.
        """
        if level not in (LEVEL_FULL, LEVEL_SCORE_ONLY):
            return False, f"Livello di pubblicazione sconosciuto: {level!r}."

        if report.status not in [MatchReport.Status.VALIDATED, MatchReport.Status.PUBLISHED]:
            return False, f"Il referto deve essere in stato VALIDATED o PUBLISHED per la pubblicazione, attuale: {report.get_status_display()}"

        # --- GUARDRAIL DOWNGRADE DI LIVELLO (D3) ---
        # Un republish che porta un referto gia' pubblicato FULL a SCORE_ONLY
        # DISTRUGGE la cronologia eventi gia' pubblica: richiede una motivazione
        # esplicita, sullo stesso principio del guardrail dato-verificato.
        # L'upgrade SCORE_ONLY->FULL e il primo publish sono liberi.
        is_downgrade = (
            report.status == MatchReport.Status.PUBLISHED
            and report.publication_level == LEVEL_FULL
            and level == LEVEL_SCORE_ONLY
        )
        if is_downgrade and (not reason or not str(reason).strip()):
            logger.warning(
                f"Referto {report.id} downgrade FULL->SCORE_ONLY RIFIUTATO: reason mancante."
            )
            return False, (
                "Downgrade del livello di pubblicazione da FULL a SCORE_ONLY rifiutato: "
                "declassare un referto gia' pubblicato con eventi ne cancella la "
                "cronologia pubblica, quindi la motivazione e' obbligatoria e non puo' "
                "essere vuota."
            )

        data = report.normalized_data
        if not data:
            return False, "Nessun dato normalizzato presente nel referto."

        # --- PUBLISH READINESS CHECK (al livello dichiarato) ---
        safe, blockers, warnings = OCRSchemaValidator.assess_publish_readiness(data, level=level)
        
        if not safe and not force:
            blocker_msg = "; ".join(blockers)
            logger.warning(f"Referto {report.id} BLOCCATO dalla pubblicazione: {blocker_msg}")
            return False, f"Pubblicazione bloccata: {blocker_msg}"
        
        if not safe and force:
            logger.warning(f"Referto {report.id} PUBBLICAZIONE FORZATA (Override Guardrails) da {user.username if user else 'N/A'}. Blocchi ignorati: {blockers}")
        
        if warnings:
            logger.info(f"Referto {report.id} pubblicazione con avvisi: {'; '.join(warnings)}")

        match = report.match

        # --- GUARDRAIL DATO VERIFICATO ---
        # Valutato anche quando `assess_publish_readiness` dice safe: quello
        # giudica la qualita' del referto, questo difende un dato gia' verificato
        # da un umano. Sono due domande diverse e nessuna implica l'altra.
        match_params = MatchDataConverter.get_match_scores(data)
        conflict = detect_verified_projection_conflict(match, match_params)

        if conflict:
            summary = _conflict_summary(conflict)
            if not force:
                logger.warning(
                    f"Referto {report.id} BLOCCATO: proiezione distruttiva su match "
                    f"{match.id} con dato verificato ({summary})."
                )
                return False, (
                    "Pubblicazione bloccata: il risultato di questa partita e' stato "
                    f"verificato a mano e i dati del referto divergono ({summary}). "
                    "Pubblicare sovrascriverebbe un dato verificato. Per procedere serve "
                    "una pubblicazione forzata con motivazione esplicita."
                )
            if not reason or not str(reason).strip():
                logger.warning(
                    f"Referto {report.id} force RIFIUTATO: reason mancante su match "
                    f"{match.id} con dato verificato ({summary})."
                )
                return False, (
                    "Pubblicazione forzata rifiutata: su una partita con dato verificato "
                    "la motivazione e' obbligatoria e non puo' essere vuota — sovrascrivere "
                    "una verifica umana senza dire perche' non e' ricostruibile a posteriori."
                )

        # Stato di partenza catturato per audit post-rollback (vedi guardrail Zero Events)
        original_status = report.status
        _abort_triggered = False
        _abort_message = None
        _abort_audit_payload = None

        try:
            with transaction.atomic():
                # Blocchiamo la riga per prevenire race conditions
                report = MatchReport.objects.select_for_update().get(id=report.id)

                # Check status safe against concurrent changes
                if report.status not in [MatchReport.Status.VALIDATED, MatchReport.Status.PUBLISHED]:
                    return False, f"La pubblicazione è bloccata, stato cambiato da transazione concorrente."

                is_republish = report.status == MatchReport.Status.PUBLISHED

                # 1. Aggiornamento Match (Punteggi e Quarti) via Converter
                # `match_params` e' gia' stato calcolato sopra per il guardrail:
                # `get_match_scores` e' puro su `data`, che qui non e' cambiato.
                match.home_score = match_params["home_score"]
                match.away_score = match_params["away_score"]
                match.quarter_scores = match_params["quarter_scores"]
                match.is_finished = True
                match.save(update_fields=['home_score', 'away_score', 'quarter_scores', 'is_finished'])

                # 1-bis. Ritiro della verifica umana dopo una sovrascrittura forzata.
                # I valori appena scritti NON sono piu' quelli che un umano ha
                # collazionato sul cartaceo, quindi `is_data_verified=True` sarebbe
                # un'affermazione falsa. Si ritira via seam (mai scrittura diretta).
                # Il risultato NON sparisce dal pubblico: `result_visibility` lo
                # rende pubblico anche per la presenza di un referto PUBLISHED, che
                # questo publish sta creando. Cambia la *pretesa*, non la visibilita':
                # da "verificato da un umano" a "pubblicato dal workflow referto".
                if conflict:
                    set_data_verified(
                        match, False, user,
                        reason=(
                            f"Ritirata automaticamente: pubblicazione forzata del referto "
                            f"{report.id} ha sovrascritto dati verificati a mano "
                            f"({_conflict_summary(conflict)}). "
                            f"Motivazione dell'operatore: {str(reason).strip()}"
                        ),
                    )

                # 2. Creazione MatchEvent via Converter + Reconciliation
                # Recupero atleti precedentemente coinvolti per ricalcolo post-cancellazione (Hardening Sync)
                previously_involved_ids = set(MatchEvent.objects.filter(match=match).exclude(player_id__isnull=True).values_list('player_id', flat=True))

                # Eliminazione preventiva eventi (Idempotenza Re-publish)
                deleted_events_count, _ = MatchEvent.objects.filter(match=match).delete()

                from accounts.models import AthleteProfile
                created_events_count = 0
                involved_athlete_ids = set()

                if level == LEVEL_SCORE_ONLY:
                    # SCORE_ONLY (Opzione A): nessun evento creato. Gli eventi
                    # esistenti sono gia' stati cancellati sopra (D1): il referto
                    # dichiara "eventi non disponibili", nessun evento puo'
                    # restare attribuito. L'abort zero-eventi NON si valuta: zero
                    # eventi qui e' il contratto del livello, non un'anomalia.
                    pass
                else:
                    events_data = MatchDataConverter.get_events_data(data)
                    for ed in events_data:
                        # Determiniamo il team corretto
                        target_team = None
                        if ed["team"] == "home":
                            target_team = match.home_team
                        elif ed["team"] == "away":
                            target_team = match.away_team

                        if not target_team:
                            continue # Team non configurato nel match

                        # Creiamo l'evento solo se abbiamo un player_id (Reconciled)
                        if ed["player_id"]:
                            # Protezione: Verifica che il player appartenga effettivamente al team target
                            if AthleteProfile.objects.filter(user_id=ed["player_id"], current_team=target_team).exists():
                                MatchEvent.objects.create(
                                    match=match,
                                    event_type=ed["event_type"],
                                    team=target_team,
                                    player_id=ed["player_id"],
                                    minute=ed["minute"] or 0,
                                    quarter=ed.get("quarter") or 1,
                                    is_penalty=ed.get("is_penalty", False),
                                    notes=ed["notes"]
                                )
                                created_events_count += 1
                                involved_athlete_ids.add(ed["player_id"])
                            else:
                                logger.warning(f"Player ID {ed['player_id']} riconciliato con team sbagliato {target_team}. Evento saltato.")

                # GUARDRAIL Policy A: 0 events created with positive score → abort
                # Anche con force=True. Previene drift sulle statistiche atleti.
                # Valutato SOLO sul livello FULL: su SCORE_ONLY zero eventi e' il
                # contratto dichiarato del livello, non un'anomalia da abortire.
                if level == LEVEL_FULL and created_events_count == 0 and (match.home_score > 0 or match.away_score > 0):
                    transaction.set_rollback(True)
                    _abort_message = (
                        f"Pubblicazione abortita: 0 eventi creati con score "
                        f"{match.home_score}-{match.away_score}. "
                        f"Verificare riconciliazione roster prima di ripubblicare."
                    )
                    logger.critical(
                        f"Referto {report.id} ABORT POST-CONVERSIONE: "
                        f"created_events_count=0, score={match.home_score}-{match.away_score}, "
                        f"force={force}, user={user.username if user else 'N/A'}"
                    )
                    _abort_audit_payload = {
                        "report_id": report.id,
                        "match_id": match.id,
                        "home_score": match.home_score,
                        "away_score": match.away_score,
                        "events_data_count": len(events_data),
                        "force": force,
                        "blockers_at_publish": blockers if not safe else [],
                    }
                    _abort_triggered = True

                if not _abort_triggered:
                    # 3. Transizione di stato referto (Singolarità del Source of Truth)
                    # Downgrading explicitly any other published reports to maintain 1:1 live sync visual guarantee.
                    # Adding an internal note to track the supersede event for operators.
                    old_reports = MatchReport.objects.filter(match=match, status=MatchReport.Status.PUBLISHED).exclude(id=report.id)
                    for old in old_reports:
                        old.status = MatchReport.Status.VALIDATED
                        old.internal_notes = (old.internal_notes or "") + f"\n[{timezone.now().strftime('%d/%m/%Y %H:%M')}] DE-PUBBLICATO: Superato da nuova versione (Report ID {report.id})."
                        old.save(update_fields=['status', 'internal_notes'])
                        # Audit trail per de-pubblicazione
                        from matches.models import MatchReportAuditLog
                        MatchReportAuditLog.objects.create(
                            report=old,
                            user=user,
                            action='depublish',
                            old_status='PUBLISHED',
                            new_status='VALIDATED',
                            reason=f'Superato da nuova versione (Report ID {report.id})',
                        )

                    report.status = MatchReport.Status.PUBLISHED
                    report.published_by = user
                    report.published_at = timezone.now()
                    # Il livello di pubblicazione si scrive SOLO qui, nello stesso
                    # save() della transizione a PUBLISHED (Opzione A).
                    report.publication_level = level
                    report.save(update_fields=['status', 'published_by', 'published_at', 'publication_level'])

                    # 3.4 Aggiornamento Statistiche Atleti (Dati derivati)
                    # Eseguito DOPO la transizione a PUBLISHED perché update_stats() ora
                    # filtra MatchEvent per match__reports__status=PUBLISHED.
                    # Uniamo atleti nuovi e atleti vecchi per garantire coerenza in caso di rimozione/spostamento (No drift).
                    all_athletes_to_update = involved_athlete_ids.union(previously_involved_ids)

                    for athlete_id in all_athletes_to_update:
                        try:
                            athlete = AthleteProfile.objects.get(user_id=athlete_id)
                            athlete.update_stats()
                        except AthleteProfile.DoesNotExist:
                            pass

                    # 3.5 Audit Trail (MatchReportAuditLog) per publish
                    from matches.models import MatchReportAuditLog
                    MatchReportAuditLog.objects.create(
                        report=report,
                        user=user,
                        action='publish' if not is_republish else 'republish',
                        old_status='VALIDATED',
                        new_status='PUBLISHED',
                        reason=reason or ('Pubblicazione forzata (override blocchi)' if force and not safe else ''),
                        after={
                            'events_deleted': deleted_events_count,
                            'events_created': created_events_count,
                            'publication_level': level,
                            'forced': force,
                            'warnings': warnings,
                        }
                    )

                    # 3.6 Audit dedicato della sovrascrittura di un dato verificato.
                    # Riga separata da quella di publish: qui interessano i valori
                    # prima/dopo e il perche', non il conteggio degli eventi.
                    if conflict:
                        MatchReportAuditLog.objects.create(
                            report=report,
                            user=user,
                            action=FORCED_OVERWRITE_AUDIT_ACTION,
                            old_status='VALIDATED',
                            new_status='PUBLISHED',
                            reason=str(reason).strip(),
                            before=conflict['before'],
                            after={
                                **conflict['after'],
                                'diverging_fields': conflict['diverging_fields'],
                                'match_id': match.id,
                            },
                        )

                    # 4. Ricalcolo Immediato Classifiche (sincrono, transazionale)
                    # Sostituisce il vecchio flag 'needs_rebuild' (differito) che non
                    # veniva mai consumato automaticamente, causando [MISSING_RECORD]
                    # per squadre senza un LeagueStanding pre-esistente.
                    # StandingsService.rebuild_for_league() è idempotente:
                    # cancella i vecchi record e li ricrea sempre da zero partendo
                    # dai match pubblicati — la stessa logica di `manage.py rebuild_standings`.
                    if match.league:
                        standings_count = StandingsService.rebuild_for_league(match.league)
                        logger.info(
                            f"Classifica lega '{match.league}' ricalcolata post-publish: "
                            f"{standings_count} record aggiornati/creati."
                        )

                    # 5. Audit Log Formale
                    audit_action = "REPUBLISH_REPORT" if is_republish else "PUBLISH_REPORT"
                    AuditLog.objects.create(
                        user=user,
                        society=match.home_team.society if (match and match.home_team) else None,
                        action=audit_action,
                        target_id=str(report.id),
                        target_type="MatchReport",
                        details={
                            "is_republish": is_republish,
                            "events_deleted": deleted_events_count,
                            "events_created": created_events_count,
                            "publication_level": level,
                            "warnings": warnings,
                            "forced": force,
                            "overridden_blockers": blockers if force and not safe else []
                        }
                    )

                    action_str = "Ripubblicato" if is_republish else "Pubblicato"
                    if force and not safe:
                        action_str = f"FORZATO ({action_str})"
                    if level == LEVEL_SCORE_ONLY:
                        msg = (f"{action_str} (SOLO PUNTEGGIO): Match aggiornato, "
                               f"{deleted_events_count} eventi rimossi, nessun evento creato "
                               f"(cronologia non disponibile).")
                    else:
                        msg = f"{action_str}: Match aggiornato, {deleted_events_count} vecchi eventi cancellati, creati {created_events_count} eventi statistici."
                    if conflict:
                        msg += (
                            " ATTENZIONE: sovrascritti dati verificati a mano; "
                            "il flag 'dato verificato' e' stato ritirato e la partita "
                            "va riverificata sul referto cartaceo."
                        )
                    if warnings:
                        msg += f" Avvisi: {len(warnings)}."
                    logger.info(f"Referto {report.id} {audit_action} con successo. {msg}")
                    return True, msg

            # ABORT path post-rollback: audit log persistente in transazione separata
            if _abort_triggered:
                try:
                    with transaction.atomic():
                        from matches.models import MatchReportAuditLog
                        MatchReportAuditLog.objects.create(
                            report=report,
                            user=user,
                            action='abort_zero_events',
                            old_status=original_status,
                            new_status=original_status,
                            reason=_abort_message,
                            after=_abort_audit_payload,
                        )
                except Exception as audit_err:
                    logger.error(f"Audit log post-abort fallito per report {report.id}: {audit_err}")
                return False, _abort_message

        except Exception as e:
            logger.error(f"Errore transazionale durante la pubblicazione del referto {report.id}: {str(e)}")
            return False, f"Errore interno durante la pubblicazione: {str(e)}"
