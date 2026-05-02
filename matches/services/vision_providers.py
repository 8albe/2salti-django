import logging
import json
from typing import Dict, Any, Tuple
from django.utils import timezone

logger = logging.getLogger(__name__)

class BaseVisionProvider:
    """
    Interfaccia base per i provider OCR/Vision.
    Ogni nuovo provider (es. Google Vision, OpenAI GPT-4o, AWS Textract) 
    deve ereditare da questa classe e implementare extract_data.
    """
    def extract_data(self, match_report) -> Tuple[Dict[str, Any], str]:
        raise NotImplementedError("Il metodo extract_data deve essere implementato dal provider.")

class MockVisionProvider(BaseVisionProvider):
    """
    Provider Mock che simula un'estrazione OCR perfetta usando i dati del database.
    Usato per test e sviluppo senza chiamate a servizi esterni.
    """
    def extract_data(self, match_report) -> Tuple[Dict[str, Any], str]:
        match = match_report.match
        
        logger.info(f"[MockVisionProvider] Simulo estrazione per report {match_report.id}")

        data = {
            "metadata": {
                "schema_version": "2.0",
                "provider": "MockVisionProvider-v1",
                "extracted_at": timezone.now().isoformat(),
                "confidence": 0.98,
                "confidence_fields": {
                    "home_team": 0.99,
                    "away_team": 0.99,
                    "final_score": 0.99,
                    "quarters": 0.95,
                    "home_roster": 0.90,
                    "away_roster": 0.90,
                    "events": 0.85,
                    "officials": 0.80,
                },
                "extraction_warnings": []
            },
            "match_info": {
                "home_team": match.home_team.society.name if match.home_team else "Unknown Home",
                "away_team": match.away_team.society.name if match.away_team else "Unknown Away",
                "competition": match.league.name if match.league else "Unknown Competition",
                "date": match.match_date.strftime("%Y-%m-%d") if match.match_date else None,
                "city": match.location or "Not specified",
                "venue": None,
                "round": None,
                "group": None,
            },
            "officials": {
                "confidence": 0.80,
                "referees": [
                    {"name": "Arbitro Mock Primo", "role": "1st"},
                    {"name": "Arbitro Mock Secondo", "role": "2nd"},
                ],
                "timekeeper": "Segnapunti Mock",
            },
            "teams": {
                "home": {
                    "name": match.home_team.society.name if match.home_team else "Home",
                    "coach": "Allenatore Mock Casa",
                    "confidence": 0.90,
                    "players": [
                        {"number": 1, "name": "Portiere Mock"},
                        {"number": 10, "name": "Capitano Mock"}
                    ]
                },
                "away": {
                    "name": match.away_team.society.name if match.away_team else "Away",
                    "coach": "Allenatore Mock Ospite",
                    "confidence": 0.90,
                    "players": [
                        {"number": 1, "name": "Opponente Mock"},
                        {"number": 5, "name": "Difensore Mock"}
                    ]
                }
            },
            "scores": {
                "final_score": f"{match.home_score or 0}-{match.away_score or 0}",
                "quarters": match.quarter_scores or {}
            },
            "events": [
                {"type": "GOAL", "player_name": "Capitano Mock", "minute": 5, "team": "home", "quarter": 1},
                {"type": "EXCLUSION_20", "player_name": "Difensore Mock", "minute": 15, "team": "away", "quarter": 2},
                {"type": "TIMEOUT", "player_name": None, "minute": 18, "team": "home", "quarter": 2, "sanction_duration": None},
            ],
            "notes": "Estrazione simulata dal MockVisionProvider v2."
        }
        
        raw_content = json.dumps(data, indent=4, ensure_ascii=False)
        return data, raw_content


class GPT4oVisionProvider(BaseVisionProvider):
    """
    Provider reale che utilizza OpenAI GPT-4o Vision per estrarre dati dal referto.
    Hardened v2: per-field confidence, ambiguity channel, null-preference enforcement.
    """
    def __init__(self):
        from django.conf import settings
        from openai import OpenAI
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def extract_data(self, match_report) -> Dict[str, Any]:
        import base64
        import json
        import os
        from .image_preprocessor import ImagePreprocessor
        
        logger.info(f"[GPT4oVisionProvider] Avvio preprocessing per report {match_report.id}...")
        
        # Safe access guard (Root cause hardening)
        if not match_report.file:
            raise ValueError("Il referto non ha alcun file associato. Impossibile eseguire OCR.")

        # Preprocessing
        original_path = match_report.file.path
        processed_path = ImagePreprocessor.process(original_path)
        
        logger.info(f"[GPT4oVisionProvider] Invio report preprocessato a OpenAI: {processed_path}")

        # Encoding dell'immagine preprocessata
        with open(processed_path, 'rb') as f:
            base64_image = base64.b64encode(f.read()).decode('utf-8')

        # Hardened v2 prompt — per-field confidence + null preference + ambiguity channel
        system_prompt = """
        Sei un esperto di analisi di referti di partite di pallanuoto (FIN - GUG). 
        Riceverai la FOTO di un referto ufficiale. Segui queste istruzioni spaziali:
        
        1. SQUADRE E PUNTEGGIO:
           - In alto a sinistra (Tabella 1): Squadra CASA (es. POL. DELTA). 'Risultato finale' è il numero in fondo a questa casella.
           - In basso a sinistra (Tabella 2): Squadra OSPITE (es. VILLA YORK). 'Risultato finale' è il numero in fondo a questa casella.
           - Punteggi parziali: Nella tabella 'Risultati parziali' al centro.
        
        2. ROSTER (GIOCATORI):
           - Sotto il nome di ogni squadra c'è l'elenco 'Giocatori'. Estrai 'N.' (numero calottina) e 'Cognome e Nome'.
           - Un roster tipico ha tra 7 e 15 giocatori per squadra.
        
        3. EVENTI (CRONOLOGIA):
           - TABELLE A DESTRA ('STORIA CRONOMETRICA'): Elenca tutti gli eventi.
           - Colonne: Tempo (Minuto), N. Calottina (chi fa l'azione), Evento (GOL, ET per Esclusione 20", TR per Rigore, ecc.).
           - Importante: Trascrivi i gol (GOL) e le espulsioni (ET come EXCLUSION_20).
        
        REGOLE CRITICHE:
        - Se un dato è ILLEGGIBILE, PARZIALE o AMBIGUO: usa null. NON INDOVINARE MAI.
        - Se un nome è parzialmente leggibile, trascrivi solo le lettere chiare e aggiungi "?" (es. "ROSS?" o "M?RETTI").
        - Se un numero è ambiguo (es. potrebbe essere 3 o 8), usa null e segnalalo in extraction_warnings.
        - Se il punteggio di un quarto non è leggibile, usa null per quel quarto.
        
        FORMATO JSON RICHIESTO:
        {
            "metadata": {
                "schema_version": "2.0",
                "confidence": <0.0-1.0 fiducia complessiva>,
                "confidence_fields": {
                    "home_team": <0.0-1.0>,
                    "away_team": <0.0-1.0>,
                    "final_score": <0.0-1.0>,
                    "quarters": <0.0-1.0>,
                    "home_roster": <0.0-1.0>,
                    "away_roster": <0.0-1.0>,
                    "events": <0.0-1.0>,
                    "officials": <0.0-1.0>
                },
                "extraction_warnings": [
                    "<stringa che descrive ogni campo ambiguo o parzialmente leggibile>"
                ]
            },
            "match_info": {
                "home_team": "<nome squadra o null>",
                "away_team": "<nome squadra o null>",
                "competition": "<nome campionato o null>",
                "date": "<YYYY-MM-DD o null se illeggibile>",
                "city": "<città o null>",
                "venue": "<nome impianto specifico (es: Piscina Comunale) o null>",
                "round": "<giornata/fase (es: Giornata 5, Finale) o null>",
                "group": "<girone (es: Girone A) o null>"
            },
            "officials": {
                "confidence": <0.0-1.0 fiducia sulla lettura degli ufficiali>,
                "referees": [
                    {"name": "<COGNOME NOME o null>", "role": "1st|2nd|null"}
                ],
                "timekeeper": "<nome segnapunti o null>"
            },
            "scores": {
                "final_score": "<X-Y o null>",
                "quarters": {
                    "1": [<home, away> o null],
                    "2": [<home, away> o null],
                    "3": [<home, away> or null],
                    "4": [<home, away> o null]
                }
            },
            "teams": {
                "home": {
                    "name": "<nome>",
                    "coach": "<nome allenatore o null>",
                    "confidence": <0.0-1.0 fiducia sulla lettura del roster>,
                    "players": [{"number": <int o null>, "name": "<cognome nome>"}]
                },
                "away": {
                    "name": "<nome>",
                    "coach": "<nome allenatore o null>",
                    "confidence": <0.0-1.0 fiducia sulla lettura del roster>,
                    "players": [{"number": <int o null>, "name": "<cognome nome>"}]
                }
            },
            "events": [
                {
                    "type": "GOAL|EXCLUSION_20|EXCLUSION_DEF|PENALTY_GOAL|PENALTY_MISSED|RED_CARD|YELLOW_CARD|TIMEOUT|OTHER",
                    "player_name": "<nome giocatore o null (null per timeout squadra)>",
                    "team": "home|away",
                    "minute": <int o null>,
                    "quarter": <int o null>,
                    "sanction_duration": <null o intero secondi (es: 20 per esclusione 20 secondi)>
                }
            ]
        }
        
        Rispondi SOLO con il JSON. Non aggiungere testo, commenti o markdown.
        """

        user_content = [
            {
                "type": "text",
                "text": "Estrai i dati da questo referto fotografato. Rispondi solo con il JSON."
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                }
            }
        ]

        try:
            import json
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                response_format={"type": "json_object"},
                max_tokens=4000
            )
            
            # Parsing robusto
            content = response.choices[0].message.content
            logger.info(f"[GPT4oVisionProvider] Risposta OpenAI ricevuta (lunghezza: {len(content) if content else 0})")
            
            if not content:
                if hasattr(response.choices[0].message, 'refusal') and response.choices[0].message.refusal:
                    logger.error(f"[GPT4oVisionProvider] OpenAI ha rifiutato la richiesta: {response.choices[0].message.refusal}")
                    raise Exception(f"OpenAI Refusal: {response.choices[0].message.refusal}")
                raise Exception("OpenAI ha restituito un contenuto vuoto.")

            data = json.loads(content)
            
            # Normalize the response to ensure consistent structure
            data = self._normalize_response(data, processed_path, original_path)
            
            # Pulizia file temporaneo se diverso dall'originale
            if processed_path != original_path and os.path.exists(processed_path):
                pass  # Keep for debug

            return data, content
            
        except Exception as e:
            logger.error(f"Errore GPT-4o: {str(e)}")
            raise Exception(f"Errore durante la chiamata a OpenAI: {str(e)}")

    @staticmethod
    def _normalize_response(data: Dict[str, Any], processed_path: str, original_path: str) -> Dict[str, Any]:
        """
        Normalize GPT-4o response to ensure consistent structure.
        Fills in missing optional sections with safe defaults.
        Trims whitespace from string fields.
        """
        # Ensure metadata structure
        if "metadata" not in data:
            data["metadata"] = {}
        meta = data["metadata"]
        meta.setdefault("schema_version", "2.0")
        meta.setdefault("confidence", 0.5)
        meta.setdefault("confidence_fields", {})
        meta.setdefault("extraction_warnings", [])
        meta.update({
            "provider": "GPT4oVisionProvider-v2-hardened",
            "extracted_at": timezone.now().isoformat(),
            "model": "gpt-4o",
            "preprocessed": processed_path != original_path
        })

        # Ensure match_info
        data.setdefault("match_info", {})
        info = data["match_info"]
        info.setdefault("home_team", None)
        info.setdefault("away_team", None)
        info.setdefault("date", None)
        # v2 optional fields
        info.setdefault("venue", None)
        info.setdefault("round", None)
        info.setdefault("group", None)
        # Trim whitespace from string fields
        for k in ["home_team", "away_team", "competition", "city", "venue", "round", "group"]:
            if isinstance(info.get(k), str):
                info[k] = info[k].strip()

        # Ensure officials structure (v2 — opzionale)
        data.setdefault("officials", {
            "confidence": None,
            "referees": [],
            "timekeeper": None,
        })
        officials = data["officials"]
        if isinstance(officials, dict):
            officials.setdefault("confidence", None)
            officials.setdefault("referees", [])
            officials.setdefault("timekeeper", None)
            # Trim referee names
            for ref in officials.get("referees", []):
                if isinstance(ref, dict) and isinstance(ref.get("name"), str):
                    ref["name"] = ref["name"].strip()

        # Ensure scores structure
        data.setdefault("scores", {})
        scores = data["scores"]
        if isinstance(scores.get("final_score"), str):
            scores["final_score"] = scores["final_score"].strip()
        scores.setdefault("quarters", {})

        # Ensure teams structure
        data.setdefault("teams", {"home": {"name": None, "players": []}, "away": {"name": None, "players": []}})
        for side in ["home", "away"]:
            team = data["teams"].setdefault(side, {"name": None, "players": []})
            team.setdefault("players", [])
            # v2 optional team fields
            team.setdefault("coach", None)
            team.setdefault("confidence", None)
            # Trim player names
            for p in team.get("players", []):
                if isinstance(p.get("name"), str):
                    p["name"] = p["name"].strip()

        # Ensure events structure
        data.setdefault("events", [])

        return data
