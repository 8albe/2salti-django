import logging
import json
import base64
import time
import os
from typing import Dict, Any, Optional
from django.conf import settings
from django.utils import timezone
from openai import OpenAI
from .base import BaseOCRProvider
from matches.models import OCRRawResponse, MatchReport
from ..image_preprocessor import ImagePreprocessor

logger = logging.getLogger(__name__)

class OpenAIProvider(BaseOCRProvider):
    """
    Concrete implementation of OpenAI GPT-4o Vision provider.
    Follows the BaseOCRProvider contract and handles OCRRawResponse persistence.
    """

    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    @property
    def provider_id(self) -> str:
        return "openai-gpt4o"

    def process_document(self, file_path: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Processes a document (image/PDF) using GPT-4o Vision.
        Saves the raw response to OCRRawResponse.
        """
        logger.info(f"[OpenAIProvider] Processing document: {file_path}")
        
        # 1. Preprocessing
        processed_path = ImagePreprocessor.process(file_path)
        logger.info(f"[OpenAIProvider] Document preprocessed: {processed_path}")

        # 2. Encoding
        with open(processed_path, 'rb') as f:
            base64_image = base64.b64encode(f.read()).decode('utf-8')

        # 3. Prompting (V2 - Hardened)
        system_prompt = self._get_system_prompt()
        user_content = [
            {"type": "text", "text": "Estrai i dati da questo referto fotografato. Rispondi solo con il JSON."},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
        ]

        start_time = time.time()
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                response_format={"type": "json_object"},
                max_tokens=4000
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            content = response.choices[0].message.content
            
            if not content:
                raise Exception("OpenAI returned empty content.")

            data = json.loads(content)
            
            # 4. Save Raw Response
            # Note: We need a match_report ID to link the response. 
            # If context provides it, we use it.
            report_id = context.get('report_id') if context else None
            if report_id:
                try:
                    report = MatchReport.objects.get(id=report_id)
                    OCRRawResponse.objects.create(
                        report=report,
                        provider_id=self.provider_id,
                        raw_response=data,
                        status_code=200,
                        request_id=getattr(response, 'id', ''),
                        latency_ms=latency_ms
                    )
                    logger.info(f"[OpenAIProvider] OCRRawResponse saved for report {report_id}")
                except MatchReport.DoesNotExist:
                    logger.warning(f"[OpenAIProvider] MatchReport {report_id} not found. Skipping RawResponse save.")
            
            # 5. Normalization (Internal consistency)
            data = self._normalize_response(data, processed_path, file_path)
            
            return data

        except Exception as e:
            logger.error(f"[OpenAIProvider] Error during OpenAI call: {str(e)}")
            raise

    def _get_system_prompt(self) -> str:
        return """
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
                    "home_team": <0.0-1.0>, "away_team": <0.0-1.0>, "final_score": <0.0-1.0>,
                    "quarters": <0.0-1.0>, "home_roster": <0.0-1.0>, "away_roster": <0.0-1.0>,
                    "events": <0.0-1.0>, "officials": <0.0-1.0>
                },
                "extraction_warnings": ["<stringa>"]
            },
            "match_info": {
                "home_team": "<nome>", "away_team": "<nome>", "competition": "<nome>",
                "date": "<YYYY-MM-DD>", "city": "<città>", "venue": "<nome>", "round": "<giornata>", "group": "<girone>"
            },
            "officials": {
                "confidence": <0.0-1.0>,
                "referees": [{"name": "<COGNOME NOME>", "role": "1st|2nd|null"}],
                "timekeeper": "<nome>"
            },
            "scores": {
                "final_score": "<X-Y>",
                "quarters": {"1": [<home, away>], "2": [<home, away>], "3": [<home, away>], "4": [<home, away>]}
            },
            "teams": {
                "home": {"name": "<nome>", "coach": "<nome>", "confidence": <0.0-1.0>, "players": [{"number": <int>, "name": "<cognome nome>"}]},
                "away": {"name": "<nome>", "coach": "<nome>", "confidence": <0.0-1.0>, "players": [{"number": <int>, "name": "<cognome nome>"}]}
            },
            "events": [
                {
                    "type": "GOAL|EXCLUSION_20|EXCLUSION_BRUTAL|PENALTY_GOAL|PENALTY_MISSED|RED_CARD|YELLOW_CARD|TIMEOUT|OTHER",
                    "player_name": "<nome>", "team": "home|away", "minute": <int>, "quarter": <int>,
                    "sanction_duration": <null|int secondi>
                }
            ]
        }
        
        Rispondi SOLO con il JSON. Non aggiungere testo, commenti o markdown.
        """

    def _normalize_response(self, data: Dict[str, Any], processed_path: str, original_path: str) -> Dict[str, Any]:
        """Internal normalization based on GPT4oVisionProvider's logic."""
        if "metadata" not in data: data["metadata"] = {}
        meta = data["metadata"]
        meta.setdefault("schema_version", "2.0")
        meta.setdefault("confidence", 0.5)
        meta.setdefault("confidence_fields", {})
        meta.update({
            "provider": self.provider_id,
            "extracted_at": timezone.now().isoformat(),
            "model": "gpt-4o",
            "preprocessed": processed_path != original_path
        })
        return data
