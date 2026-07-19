"""
Test per GeminiVisionProvider e per la selezione del provider Gemini dalla factory.

L'SDK google-genai è SEMPRE mockato: nessuna chiamata reale a Gemini e nessuna
dipendenza dal pacchetto realmente installato (inseriamo un modulo fake in
sys.modules). Coerente con la regola "mai chiamate reali all'LLM nei test".
"""
import json
import os
import sys
import tempfile
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

# Forza il caricamento pulito di cv2 (via ImagePreprocessor) PRIMA di qualunque
# patch.dict(sys.modules): cv2 non può essere ricaricato una seconda volta nel
# processo, e caricarlo mentre sys.modules è patchato lo romperebbe.
import matches.services.image_preprocessor  # noqa: F401
from matches.services.ocr_service import OCRService
from matches.services.vision_providers import GeminiVisionProvider


def _fake_genai_modules():
    """Costruisce fake google / google.genai / google.genai.types per sys.modules."""
    fake_types = ModuleType("google.genai.types")
    fake_types.Part = MagicMock()
    fake_types.Part.from_bytes = MagicMock(return_value="FAKE_PART")
    fake_types.GenerateContentConfig = MagicMock(return_value="FAKE_CONFIG")
    fake_genai = ModuleType("google.genai")
    fake_genai.types = fake_types
    fake_genai.Client = MagicMock()
    fake_google = ModuleType("google")
    fake_google.genai = fake_genai
    return {
        "google": fake_google,
        "google.genai": fake_genai,
        "google.genai.types": fake_types,
    }


def _gemini_json_payload(model):
    """Payload JSON grezzo (pre-normalizzazione) in schema OCR v2."""
    return json.dumps({
        "metadata": {"confidence": 0.88, "confidence_fields": {"home_team": 0.9}},
        "match_info": {"home_team": "  POL. DELTA  ", "away_team": "VILLA YORK"},
        "scores": {"final_score": "10-8", "quarters": {"1": [3, 2], "2": [2, 2]}},
        "teams": {
            "home": {"players": [{"number": 1, "name": " Portiere "}]},
            "away": {"players": [{"number": 1, "name": "Opponente"}]},
        },
        "events": [{"type": "GOAL", "team": "home", "minute": 5}],
    })


class GeminiVisionProviderTest(TestCase):
    def setUp(self):
        fd, self.image_path = tempfile.mkstemp(suffix=".jpg")
        with os.fdopen(fd, "wb") as f:
            f.write(b"fake image bytes")
        self.addCleanup(os.remove, self.image_path)
        self.report = SimpleNamespace(
            id="bench:test",
            file=SimpleNamespace(path=self.image_path),
        )

    def _make_provider(self, response):
        """Provider con __init__ bypassato e client mockato che ritorna `response`."""
        provider = GeminiVisionProvider.__new__(GeminiVisionProvider)
        provider.client = MagicMock()
        provider.client.models.generate_content.return_value = response
        return provider

    def test_extract_data_returns_v2_schema_no_preprocess(self):
        response = SimpleNamespace(
            text=_gemini_json_payload("gemini-2.5-flash"),
            usage_metadata=SimpleNamespace(
                prompt_token_count=1200, candidates_token_count=300
            ),
        )
        provider = self._make_provider(response)
        sent = []

        with patch.dict(sys.modules, _fake_genai_modules()):
            data, raw = provider.extract_data(
                self.report,
                model="gemini-2.5-flash",
                preprocess=False,
                sent_image_callback=sent.append,
            )

        # Ritorno = (dict, raw_content_str)
        self.assertIsInstance(data, dict)
        self.assertIsInstance(raw, str)

        # sent_image_callback riceve il path dei byte inviati (grezzi con no-preprocess)
        self.assertEqual(sent, [self.image_path])

        # Schema OCR v2 normalizzato + provenienza Gemini
        meta = data["metadata"]
        self.assertEqual(meta["provider"], "GeminiVisionProvider-v1")
        self.assertEqual(meta["model"], "gemini-2.5-flash")
        self.assertFalse(meta["preprocessed"])
        self.assertEqual(meta["schema_version"], "2.0")
        # token_usage mappato da usage_metadata
        self.assertEqual(meta["token_usage"], {
            "prompt_tokens": 1200, "completion_tokens": 300,
        })

        # Sezioni schema presenti + trimming stringhe
        self.assertEqual(data["match_info"]["home_team"], "POL. DELTA")
        self.assertEqual(data["scores"]["final_score"], "10-8")
        self.assertEqual(len(data["teams"]["home"]["players"]), 1)
        self.assertEqual(data["teams"]["home"]["players"][0]["name"], "Portiere")
        self.assertEqual(len(data["events"]), 1)

        # Modello passato correttamente all'SDK
        _, call_kwargs = provider.client.models.generate_content.call_args
        self.assertEqual(call_kwargs["model"], "gemini-2.5-flash")

    def test_extract_data_respects_preprocess_true(self):
        response = SimpleNamespace(
            text=_gemini_json_payload("gemini-3.1-pro-preview"),
            usage_metadata=None,  # SDK senza usage -> token N/A
        )
        provider = self._make_provider(response)
        sent = []
        # File processato reale (evita di patchare builtins.open): il provider
        # legge questi byte e li passa all'SDK (mockato).
        fd, processed = tempfile.mkstemp(suffix=".proc.jpg")
        with os.fdopen(fd, "wb") as f:
            f.write(b"processed image bytes")
        self.addCleanup(os.remove, processed)

        with patch.dict(sys.modules, _fake_genai_modules()), \
             patch("matches.services.image_preprocessor.ImagePreprocessor.process",
                   return_value=processed) as mock_proc:
            data, _raw = provider.extract_data(
                self.report,
                model="gemini-3.1-pro-preview",
                preprocess=True,
                sent_image_callback=sent.append,
            )

        mock_proc.assert_called_once_with(self.image_path)
        # Con preprocess=True la callback riceve il path processato
        self.assertEqual(sent, [processed])
        self.assertTrue(data["metadata"]["preprocessed"])
        # usage_metadata assente -> nessun token_usage forzato
        self.assertNotIn("token_usage", data["metadata"])

    def test_empty_response_raises(self):
        response = SimpleNamespace(text="", usage_metadata=None)
        provider = self._make_provider(response)
        with patch.dict(sys.modules, _fake_genai_modules()):
            with self.assertRaises(Exception) as ctx:
                provider.extract_data(self.report, preprocess=False)
        self.assertIn("Gemini", str(ctx.exception))

    def test_uses_default_max_output_tokens(self):
        """Senza setting esplicito, il provider alza il limite di output a 32000."""
        response = SimpleNamespace(
            text=_gemini_json_payload("gemini-2.5-flash"), usage_metadata=None
        )
        provider = self._make_provider(response)
        fake_mods = _fake_genai_modules()
        with patch.dict(sys.modules, fake_mods):
            provider.extract_data(self.report, preprocess=False)
        _, cfg_kwargs = fake_mods["google.genai.types"].GenerateContentConfig.call_args
        self.assertEqual(cfg_kwargs["max_output_tokens"], 32000)

    @override_settings(OCR_MAX_OUTPUT_TOKENS=12345)
    def test_max_output_tokens_configurable_via_settings(self):
        """OCR_MAX_OUTPUT_TOKENS in settings sovrascrive il default."""
        response = SimpleNamespace(
            text=_gemini_json_payload("gemini-2.5-flash"), usage_metadata=None
        )
        provider = self._make_provider(response)
        fake_mods = _fake_genai_modules()
        with patch.dict(sys.modules, fake_mods):
            provider.extract_data(self.report, preprocess=False)
        _, cfg_kwargs = fake_mods["google.genai.types"].GenerateContentConfig.call_args
        self.assertEqual(cfg_kwargs["max_output_tokens"], 12345)

    def test_truncated_json_with_max_tokens_raises_readable(self):
        """JSON troncato + finish_reason MAX_TOKENS -> errore chiaro, non un crash grezzo."""
        truncated = '{"metadata": {"confidence": 0.9}, "events": [{"type": "GOAL", "player_name": "ROS'
        response = SimpleNamespace(
            text=truncated,
            usage_metadata=None,
            candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name="MAX_TOKENS"))],
        )
        provider = self._make_provider(response)
        with patch.dict(sys.modules, _fake_genai_modules()):
            with self.assertRaises(Exception) as ctx:
                provider.extract_data(self.report, preprocess=False)
        msg = str(ctx.exception)
        self.assertIn("troncato", msg)
        self.assertIn("MAX_TOKENS", msg)
        self.assertIn("OCR_MAX_OUTPUT_TOKENS", msg)
        # Non deve propagare un JSONDecodeError grezzo.
        self.assertNotIsInstance(ctx.exception, json.JSONDecodeError)

    def test_invalid_json_without_finish_reason_raises_readable(self):
        """JSON invalido senza finish_reason: messaggio 'troncato/invalido' leggibile."""
        response = SimpleNamespace(text="questo non e' json", usage_metadata=None)
        provider = self._make_provider(response)
        with patch.dict(sys.modules, _fake_genai_modules()):
            with self.assertRaises(Exception) as ctx:
                provider.extract_data(self.report, preprocess=False)
        self.assertIn("JSON troncato/invalido", str(ctx.exception))


class GeminiFactoryTest(TestCase):
    def setUp(self):
        OCRService._provider = None

    def tearDown(self):
        OCRService._provider = None

    @override_settings(OCR_PROVIDER="gemini", GEMINI_API_KEY="test_key")
    @patch("matches.services.vision_providers.GeminiVisionProvider.__init__", return_value=None)
    def test_gemini_provider_selected(self, mock_init):
        provider = OCRService.get_provider()
        self.assertIsInstance(provider, GeminiVisionProvider)
        mock_init.assert_called_once()

    @override_settings(OCR_PROVIDER="gemini", GEMINI_API_KEY="")
    def test_missing_gemini_key_raises(self):
        with self.assertRaises(ValueError) as ctx:
            OCRService.get_provider()
        self.assertIn("GEMINI_API_KEY mancante", str(ctx.exception))
