import json
import logging
import time
from typing import Dict, Any
from core.services.notification_service import NotificationService
from matches.models import MatchReport, Match
from .match_discovery import MatchDiscoveryService

logger = logging.getLogger(__name__)

def normalize_name(name: str) -> str:
    if not name:
        return ""
    name = name.lower().strip()
    # rimuovi suffissi OCR comuni
    if name.endswith(" v") or name.endswith(" g"):
        name = name[:-2]
    # rimuovi caratteri singoli finali solo se noti come rumore (v, g, x)
    # per evitare di rompere nomi tipo "Athlete B" o "Serie A"
    parts = name.split()
    if len(parts) > 1 and len(parts[-1]) == 1 and parts[-1] in ('v', 'g', 'x'):
        name = " ".join(parts[:-1])
    # normalizza spazi
    name = " ".join(name.split())
    return name

def simple_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0
    matches = sum(1 for x, y in zip(a, b) if x == y)
    return matches / max(len(a), len(b))

def fuzzy_match(name: str, queryset, threshold: float = 0.8):
    normalized = normalize_name(name)
    best = None
    best_score = 0
    for obj in queryset:
        target_name = ""
        if hasattr(obj, 'name'):
            target_name = obj.name
        elif hasattr(obj, 'user'):
            target_name = obj.user.get_full_name()
        
        score = simple_similarity(normalized, normalize_name(target_name))
        if score > best_score:
            best_score = score
            best = obj
    if best_score >= threshold:
        return best
    return None

def resolve_entity(name: str, queryset):
    if not name:
        return None
    # 1 exact (normalized)
    normalized = normalize_name(name)
    for obj in queryset:
        target_name = ""
        if hasattr(obj, 'name'):
            target_name = obj.name
        elif hasattr(obj, 'user'):
            target_name = obj.user.get_full_name()
            
        if normalize_name(target_name) == normalized:
            return obj
            
    # 2 fuzzy
    return fuzzy_match(name, queryset)

def tokenize(name: str):
    name = normalize_name(name)
    return name.split()

def token_match(name: str, queryset):
    tokens = set(tokenize(name))
    if not tokens: return None
    matches = []
    for obj in queryset:
        target_name = obj.user.get_full_name() if hasattr(obj, 'user') else getattr(obj, 'name', '')
        obj_tokens = set(tokenize(target_name))
        if tokens == obj_tokens:
            matches.append(obj)
    return matches[0] if len(matches) == 1 else None

def partial_token_match(name: str, queryset):
    tokens = set(tokenize(name))
    if not tokens: return None
    matches = []
    for obj in queryset:
        target_name = obj.user.get_full_name() if hasattr(obj, 'user') else getattr(obj, 'name', '')
        obj_tokens = set(tokenize(target_name))
        overlap = tokens & obj_tokens
        if len(overlap) >= 1:
            if len(overlap) >= min(len(tokens), len(obj_tokens)) / 2:
                matches.append(obj)
    return matches[0] if len(matches) == 1 else None

def initial_match(name: str, queryset):
    name = normalize_name(name)
    if not name: return None
    matches = []
    for obj in queryset:
        target_name = obj.user.get_full_name() if hasattr(obj, 'user') else getattr(obj, 'name', '')
        obj_name = normalize_name(target_name)
        if not obj_name: continue
        # Handle single char names if they exist
        if name[0] == obj_name[0] and name[-1] == obj_name[-1]:
            matches.append(obj)
    return matches[0] if len(matches) == 1 else None

def resolve_athlete(name: str, queryset):
    if not name:
        return None
    # 1. Exact match (normalized)
    normalized = normalize_name(name)
    exact_matches = []
    for obj in queryset:
        target_name = obj.user.get_full_name() if hasattr(obj, 'user') else getattr(obj, 'name', '')
        if normalize_name(target_name) == normalized:
            exact_matches.append(obj)
    if len(exact_matches) == 1:
        return exact_matches[0]
        
    # 2. Token match
    match = token_match(name, queryset)
    if match: return match
    
    # 3. Partial Token Match
    match = partial_token_match(name, queryset)
    if match: return match
    
    # 4. Initial Match (heuristic for abbreviations)
    match = initial_match(name, queryset)
    if match: return match
    
    # 5. Fallback Fuzzy
    return fuzzy_match(name, queryset)

def normalize_team_name(name: str) -> str:
    if not name:
        return ""
    # Start with base normalization
    name = normalize_name(name)
    
    # Prefix removal (Team specific)
    prefixes = ["an ", "asd ", "ss ", "cn ", "soc ", "pol "]
    for p in prefixes:
        if name.startswith(p):
            name = name[len(p):]
            break # Remove only one prefix
            
    return name.strip()

def resolve_team_entity(name: str, queryset):
    if not name:
        return None
        
    normalized_input = normalize_team_name(name)
    
    matches = []
    # 1. Exact match on normalized team names
    for obj in queryset:
        target_name = getattr(obj, 'name', '')
        if normalize_team_name(target_name) == normalized_input:
            matches.append(obj)
            
    # Ambiguity check
    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        return None # Ambiguous match
        
    # 2. Fuzzy match on normalized team names
    best = None
    best_score = 0
    fuzzy_matches = []
    
    threshold = 0.8
    for obj in queryset:
        target_name = getattr(obj, 'name', '')
        score = simple_similarity(normalized_input, normalize_team_name(target_name))
        if score > best_score:
            best_score = score
            best = obj
            fuzzy_matches = [obj]
        elif score == best_score:
            fuzzy_matches.append(obj)
            
    if best_score >= threshold and len(fuzzy_matches) == 1:
        return best
        
    return None

class OCRService:
    """
    Servizio per l'estrazione OCR dei dati dai referti.
    Utilizza un VisionProvider per l'estrazione effettiva.
    """
    _provider = None

    @classmethod
    def get_provider(cls):
        """Ritorna il provider configurato in base ai settings."""
        if cls._provider is None:
            from django.conf import settings
            from .vision_providers import MockVisionProvider, GPT4oVisionProvider
            
            provider_type = getattr(settings, 'OCR_PROVIDER', 'mock').lower()
            
            if provider_type == 'gpt4o' or provider_type == 'openai':
                api_key = getattr(settings, 'OPENAI_API_KEY', None)
                if not api_key:
                    raise ValueError("OCR_PROVIDER configurato come 'gpt4o', ma OPENAI_API_KEY mancante.")
                try:
                    cls._provider = GPT4oVisionProvider()
                except Exception as e:
                    raise RuntimeError(f"Impossibile inizializzare GPT4oVisionProvider: {str(e)}")
            else:
                cls._provider = MockVisionProvider()
        return cls._provider

    @classmethod
    def set_provider(cls, provider):
        """Permette di iniettare un provider diverso (es. per test)."""
        cls._provider = provider

    @classmethod
    def extract_data(cls, match_report: MatchReport) -> Dict[str, Any]:
        """
        Estrae i dati da un file referto delegando al provider.
        """
        provider = cls.get_provider()
        
        # Bridge between old extract_data and new process_document interface
        if hasattr(provider, 'process_document'):
            context = {'report_id': match_report.id}
            return provider.process_document(match_report.file.path, context=context)
        
        # Fallback for old providers (like MockVisionProvider)
        return provider.extract_data(match_report)

    @staticmethod
    def process_and_update(match_report: MatchReport):
        """
        Esegue l'estrazione e aggiorna il modello MatchReport.
        Sposta lo stato a EXTRACTED.
        """
        # Idempotenza: non processare se già in corso o completato (salvo esplicito REJECTED o NEEDS_REVIEW)
        if match_report.status not in [MatchReport.Status.UPLOADED, MatchReport.Status.REJECTED, MatchReport.Status.NEEDS_REVIEW]:
            logger.warning(f"Referto {match_report.id} saltato: stato attuale {match_report.status}")
            return False

        # Verifica presenza file fisico (Root cause hardening)
        if match_report.source_channel == 'FILE' and not match_report.file:
            logger.error(f"Referto {match_report.id} (canale FILE) non ha un file associato. Transizione a REJECTED.")
            match_report.status = MatchReport.Status.REJECTED
            match_report.validation_notes = "ERRORE: Nessun file associato al referto. Impossibile procedere con OCR."
            match_report.save()
            return False

        try:
            match_report.status = MatchReport.Status.PROCESSING
            match_report.save()

            # Estrazione via Provider
            provider = OCRService.get_provider()
            start_time = time.time()
            
            # Polimorfismo: supportiamo sia l'interfaccia vecchia che la nuova
            if hasattr(provider, 'process_document'):
                context = {'report_id': match_report.id}
                data = provider.process_document(match_report.file.path, context=context)
                raw_content = json.dumps(data) # OpenAIProvider already saves the raw real response in its method
            else:
                data, raw_content = provider.extract_data(match_report)
                
            duration = round(time.time() - start_time, 2)
            logger.info(f"[OCR_TRIAL] Report {match_report.id} | Provider: {provider.__class__.__name__} | Duration: {duration}s | Confidence: {data.get('metadata', {}).get('confidence', 'N/A')}")

            # Aggiornamento campi base
            match_report.raw_api_response = raw_content
            match_report.raw_extracted_data = data
            
            # --- AUTO-RECONCILIATION ---
            normalized_data = data.copy()
            reconciliation = {
                "home_team_id": None,
                "away_team_id": None,
                "home_players": {},
                "away_players": {}
            }
            
            # --- MATCH DISCOVERY ---
            if not match_report.match:
                match = MatchDiscoveryService.discover(data)
                if match:
                    match_report.match = match
                    match_report.save()
                    logger.info(f"MatchDiscovery: Referto {match_report.id} collegato automaticamente al match {match.id}")
                else:
                    logger.warning(f"MatchDiscovery: Impossibile individuare il match per il referto {match_report.id}")
            
            match = match_report.match
            
            # Resolve Teams against linked match teams
            if resolve_team_entity(data.get('match_info', {}).get('home_team'), [match.home_team]):
                reconciliation["home_team_id"] = match.home_team.id
            
            if resolve_team_entity(data.get('match_info', {}).get('away_team'), [match.away_team]):
                reconciliation["away_team_id"] = match.away_team.id
                
            # Resolve Players against rosters
            for side in ['home', 'away']:
                team_obj = getattr(match, f"{side}_team")
                if team_obj:
                    roster = list(team_obj.get_roster())
                    side_players = data.get('teams', {}).get(side, {}).get('players', [])
                    for p_ocr in side_players:
                        p_name = p_ocr.get('name')
                        if p_name:
                            matched_athlete = resolve_athlete(p_name, roster)
                            if matched_athlete:
                                # We store the User ID since it's the target for MatchEvents
                                reconciliation[f"{side}_players"][p_name] = matched_athlete.user.id
            
            normalized_data['reconciliation'] = reconciliation
            match_report.normalized_data = normalized_data
            # --- END AUTO-RECONCILIATION ---
            
            # Valutazione Qualità OCR Gate (Header Trust Hardening)
            from .ocr_quality_gate import OCRQualityGate

            context = {}
            if match_report.match:
                context = {
                    'home_team': match_report.match.home_team.name,
                    'away_team': match_report.match.away_team.name,
                    'location': match_report.match.location
                }
            else:
                context = {
                    'home_team': data.get('match_info', {}).get('home_team', 'N/A'),
                    'away_team': data.get('match_info', {}).get('away_team', 'N/A'),
                    'location': data.get('match_info', {}).get('location', 'N/A'),
                    'no_match_linked': True
                }
            is_valid, blockers, warnings, infos = OCRQualityGate.evaluate(data, context=context)
            
            if not match_report.match:
                is_valid = False
                if "Nessun match collegato rilevato." not in blockers:
                    blockers.append("Nessun match collegato rilevato. Identificazione automatica fallita.")
            
            validation_dict = {
                "blocking": blockers,
                "warnings": warnings,
                "info": infos
            }
            
            if not is_valid:
                match_report.status = MatchReport.Status.NEEDS_REVIEW
                match_report.validation_notes = json.dumps(validation_dict)
                logger.warning(f"Referto {match_report.id} ha fallito il gate OCR. Bloccato in NEEDS_REVIEW.")
                NotificationService.notify_report_needs_review(match_report)
            else:
                match_report.status = MatchReport.Status.EXTRACTED
                match_report.validation_notes = json.dumps(validation_dict)
            
            gate_result = "PASS" if is_valid else "FAIL"
            logger.info(f"[OCR_TRIAL] Report {match_report.id} | QualityGate: {gate_result} | Blockers: {blockers} | Warnings: {warnings} | Info: {infos}")
                
            match_report.save()
            
            from management.utils import log_action
            society = match_report.match.home_team.society if match_report.match else None
            log_action(None, society, "OCR_PROCESSING_SUCCESS", target=match_report, details={"provider": provider.__class__.__name__, "ocr_valid": is_valid})
            
            logger.info(f"Referto {match_report.id} elaborato con stato {match_report.status} via {provider.__class__.__name__}")
            return True
        except Exception as e:
            provider_name = getattr(OCRService, '_provider', None)
            provider_name = provider_name.__class__.__name__ if provider_name else "Init/Config Error"
                
            logger.error(f"Errore durante l'elaborazione del referto {match_report.id}: {str(e)}")
            match_report.status = MatchReport.Status.NEEDS_REVIEW
            match_report.validation_notes = f"Errore Tecnico OCR ({provider_name}): {str(e)}"
            match_report.save()
            NotificationService.notify_report_needs_review(match_report)
            return False
