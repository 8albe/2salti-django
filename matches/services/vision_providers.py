import logging
import json
from types import SimpleNamespace
from typing import Dict, Any, Tuple
from django.utils import timezone

logger = logging.getLogger(__name__)

# Testo utente inviato insieme all'immagine del referto (condiviso tra i provider vivi).
OCR_USER_TEXT = "Estrai i dati da questo referto fotografato. Rispondi solo con il JSON."

# Prompt di sistema hardened v2 (per-field confidence + null preference + ambiguity channel).
# Condiviso 1:1 tra GPT4oVisionProvider e GeminiVisionProvider: stesso schema OCR v2 in output.
OCR_SYSTEM_PROMPT_V2 = """
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
                    "type": "GOAL|EXCLUSION_20|YELLOW_CARD|RED_CARD|TIMEOUT|OTHER",
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

    def extract_data(self, match_report, model: str = None, preprocess: bool = True,
                     sent_image_callback=None) -> Dict[str, Any]:
        """
        preprocess=False bypassa ImagePreprocessor e invia i byte grezzi del file
        (debug: nessun auto-rotate né downscale). sent_image_callback, se fornita,
        riceve il path del file i cui byte vengono effettivamente inviati al modello,
        prima della chiamata API (quindi anche in caso di errore/refusal successivo).
        """
        import base64
        import json
        import mimetypes
        import os
        from django.conf import settings
        from .image_preprocessor import ImagePreprocessor

        # Modello: override per-chiamata > settings.OCR_MODEL > default storico
        model = model or getattr(settings, "OCR_MODEL", "gpt-4o")

        logger.info(f"[GPT4oVisionProvider] Avvio preprocessing per report {match_report.id} (model={model})...")

        # Safe access guard (Root cause hardening)
        if not match_report.file:
            raise ValueError("Il referto non ha alcun file associato. Impossibile eseguire OCR.")

        # Preprocessing (bypassabile per debug)
        original_path = match_report.file.path
        if preprocess:
            processed_path = ImagePreprocessor.process(original_path)
            mime_type = "image/jpeg"
        else:
            logger.info(f"[GPT4oVisionProvider] Preprocessing bypassato per report {match_report.id}: invio immagine grezza.")
            processed_path = original_path
            mime_type = mimetypes.guess_type(processed_path)[0] or "image/jpeg"

        logger.info(f"[GPT4oVisionProvider] Invio report a OpenAI: {processed_path}")

        if sent_image_callback:
            sent_image_callback(processed_path)

        # Encoding dell'immagine effettivamente inviata
        with open(processed_path, 'rb') as f:
            base64_image = base64.b64encode(f.read()).decode('utf-8')

        system_prompt = OCR_SYSTEM_PROMPT_V2

        user_content = [
            {
                "type": "text",
                "text": OCR_USER_TEXT
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{base64_image}",
                    "detail": getattr(settings, "OCR_IMAGE_DETAIL", "high")
                }
            }
        ]

        try:
            import json
            response = self.client.chat.completions.create(
                model=model,
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
            data = self._normalize_response(
                data, processed_path, original_path,
                model=model,
                usage=getattr(response, "usage", None),
            )
            
            # Pulizia file temporaneo se diverso dall'originale
            if processed_path != original_path and os.path.exists(processed_path):
                pass  # Keep for debug

            return data, content
            
        except Exception as e:
            logger.error(f"Errore GPT-4o: {str(e)}")
            raise Exception(f"Errore durante la chiamata a OpenAI: {str(e)}")

    @staticmethod
    def _normalize_response(data: Dict[str, Any], processed_path: str, original_path: str,
                            model: str = "gpt-4o", usage=None,
                            provider: str = "GPT4oVisionProvider-v2-hardened") -> Dict[str, Any]:
        """
        Normalize a vision-provider response into the OCR v2 schema.
        Fills in missing optional sections with safe defaults.
        Trims whitespace from string fields. Condiviso da GPT4oVisionProvider e
        GeminiVisionProvider: passare `provider` per marcare la provenienza.
        `usage`, se fornito, espone .prompt_tokens / .completion_tokens.
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
            "provider": provider,
            "extracted_at": timezone.now().isoformat(),
            "model": model,
            "preprocessed": processed_path != original_path
        })
        if usage is not None:
            meta["token_usage"] = {
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
            }

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


class GeminiVisionProvider(BaseVisionProvider):
    """
    Provider reale che utilizza Google Gemini (SDK google-genai) per estrarre
    dati dal referto. Espone la STESSA interfaccia extract_data di
    GPT4oVisionProvider (stessi parametri model/preprocess/sent_image_callback,
    stesso schema OCR v2 in output, stesso prompt di sistema OCR_SYSTEM_PROMPT_V2).
    Il modello di default è letto da settings.GEMINI_MODEL con fallback a
    'gemini-2.5-flash'; --models nel bench può passare qualsiasi model string.
    """
    def __init__(self):
        from django.conf import settings
        from google import genai
        self.client = genai.Client(api_key=getattr(settings, "GEMINI_API_KEY", ""))

    def extract_data(self, match_report, model: str = None, preprocess: bool = True,
                     sent_image_callback=None) -> Tuple[Dict[str, Any], str]:
        """
        Stesso contratto di GPT4oVisionProvider.extract_data:
        preprocess=False bypassa ImagePreprocessor e invia i byte grezzi;
        sent_image_callback, se fornita, riceve il path del file effettivamente
        inviato al modello, prima della chiamata API. Ritorna (data, raw_content).
        """
        import mimetypes
        import os
        from django.conf import settings
        from google.genai import types

        # Modello: override per-chiamata > settings.GEMINI_MODEL > default
        model = model or getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")

        logger.info(f"[GeminiVisionProvider] Avvio preprocessing per report {match_report.id} (model={model})...")

        if not match_report.file:
            raise ValueError("Il referto non ha alcun file associato. Impossibile eseguire OCR.")

        # Preprocessing (bypassabile per debug) — identico al provider OpenAI.
        # Import lazy: nel path raw (preprocess=False) non tocchiamo cv2.
        original_path = match_report.file.path
        if preprocess:
            from .image_preprocessor import ImagePreprocessor
            processed_path = ImagePreprocessor.process(original_path)
            mime_type = "image/jpeg"
        else:
            logger.info(f"[GeminiVisionProvider] Preprocessing bypassato per report {match_report.id}: invio immagine grezza.")
            processed_path = original_path
            mime_type = mimetypes.guess_type(processed_path)[0] or "image/jpeg"

        logger.info(f"[GeminiVisionProvider] Invio report a Gemini: {processed_path}")

        if sent_image_callback:
            sent_image_callback(processed_path)

        with open(processed_path, "rb") as f:
            image_bytes = f.read()

        try:
            response = self.client.models.generate_content(
                model=model,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    OCR_USER_TEXT,
                ],
                config=types.GenerateContentConfig(
                    system_instruction=OCR_SYSTEM_PROMPT_V2,
                    response_mime_type="application/json",
                    max_output_tokens=4000,
                ),
            )

            content = response.text
            logger.info(f"[GeminiVisionProvider] Risposta Gemini ricevuta (lunghezza: {len(content) if content else 0})")

            if not content:
                raise Exception("Gemini ha restituito un contenuto vuoto.")

            data = json.loads(content)

            # token_usage per il confronto costi (N/A se l'SDK non lo espone)
            usage = None
            usage_meta = getattr(response, "usage_metadata", None)
            if usage_meta is not None:
                usage = SimpleNamespace(
                    prompt_tokens=getattr(usage_meta, "prompt_token_count", None),
                    completion_tokens=getattr(usage_meta, "candidates_token_count", None),
                )

            data = GPT4oVisionProvider._normalize_response(
                data, processed_path, original_path,
                model=model,
                usage=usage,
                provider="GeminiVisionProvider-v1",
            )

            return data, content

        except Exception as e:
            logger.error(f"Errore Gemini: {str(e)}")
            raise Exception(f"Errore durante la chiamata a Gemini: {str(e)}")
