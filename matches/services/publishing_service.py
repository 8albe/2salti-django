import logging
from typing import Tuple
from matches.models import MatchReport, MatchEvent
from .converters import MatchDataConverter
from .schema import OCRSchemaValidator
from .standings_service import StandingsService
from django.db import transaction
from django.utils import timezone
from management.models import AuditLog

logger = logging.getLogger(__name__)

class PublishingService:
    """
    Servizio per la pubblicazione dei dati strutturati estratti dall'OCR.
    MVP+: Aggiorna Match e crea MatchEvent se riconciliati.
    Hardened v2: semantic guardrails before publish.
    """

    @staticmethod
    def publish_report(report: MatchReport, user=None, force: bool = False, reason: str = '') -> Tuple[bool, str]:
        """
        Trasferisce i dati dal report (normalized_data) al record Match e crea eventi.
        Transactional, Idempotent, and Safe on Re-publish.
        """
        if report.status not in [MatchReport.Status.VALIDATED, MatchReport.Status.PUBLISHED]:
            return False, f"Il referto deve essere in stato VALIDATED o PUBLISHED per la pubblicazione, attuale: {report.get_status_display()}"
            
        data = report.normalized_data
        if not data:
            return False, "Nessun dato normalizzato presente nel referto."

        # --- PUBLISH READINESS CHECK ---
        safe, blockers, warnings = OCRSchemaValidator.assess_publish_readiness(data)
        
        if not safe and not force:
            blocker_msg = "; ".join(blockers)
            logger.warning(f"Referto {report.id} BLOCCATO dalla pubblicazione: {blocker_msg}")
            return False, f"Pubblicazione bloccata: {blocker_msg}"
        
        if not safe and force:
            logger.warning(f"Referto {report.id} PUBBLICAZIONE FORZATA (Override Guardrails) da {user.username if user else 'N/A'}. Blocchi ignorati: {blockers}")
        
        if warnings:
            logger.info(f"Referto {report.id} pubblicazione con avvisi: {'; '.join(warnings)}")

        match = report.match

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
                match_params = MatchDataConverter.get_match_scores(data)
                match.home_score = match_params["home_score"]
                match.away_score = match_params["away_score"]
                match.quarter_scores = match_params["quarter_scores"]
                match.is_finished = True
                match.save(update_fields=['home_score', 'away_score', 'quarter_scores', 'is_finished'])

                # 2. Creazione MatchEvent via Converter + Reconciliation
                # Recupero atleti precedentemente coinvolti per ricalcolo post-cancellazione (Hardening Sync)
                previously_involved_ids = set(MatchEvent.objects.filter(match=match).exclude(player_id__isnull=True).values_list('player_id', flat=True))

                # Eliminazione preventiva eventi (Idempotenza Re-publish)
                deleted_events_count, _ = MatchEvent.objects.filter(match=match).delete()

                events_data = MatchDataConverter.get_events_data(data)
                created_events_count = 0

                from accounts.models import AthleteProfile
                involved_athlete_ids = set()
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
                                notes=ed["notes"]
                            )
                            created_events_count += 1
                            involved_athlete_ids.add(ed["player_id"])
                        else:
                            logger.warning(f"Player ID {ed['player_id']} riconciliato con team sbagliato {target_team}. Evento saltato.")

                # GUARDRAIL Policy A: 0 events created with positive score → abort
                # Anche con force=True. Previene drift sulle statistiche atleti.
                if created_events_count == 0 and (match.home_score > 0 or match.away_score > 0):
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
                    # 2.5 Aggiornamento Statistiche Atleti (Dati derivati)
                    # Uniamo atleti nuovi e atleti vecchi per garantire coerenza in caso di rimozione/spostamento (No drift)
                    all_athletes_to_update = involved_athlete_ids.union(previously_involved_ids)

                    for athlete_id in all_athletes_to_update:
                        try:
                            athlete = AthleteProfile.objects.get(user_id=athlete_id)
                            athlete.update_stats()
                        except AthleteProfile.DoesNotExist:
                            pass

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
                    report.save(update_fields=['status', 'published_by', 'published_at'])

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
                            'forced': force,
                            'warnings': warnings,
                        }
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
                            "warnings": warnings,
                            "forced": force,
                            "overridden_blockers": blockers if force and not safe else []
                        }
                    )

                    action_str = "Ripubblicato" if is_republish else "Pubblicato"
                    if force and not safe:
                        action_str = f"FORZATO ({action_str})"
                    msg = f"{action_str}: Match aggiornato, {deleted_events_count} vecchi eventi cancellati, creati {created_events_count} eventi statistici."
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
