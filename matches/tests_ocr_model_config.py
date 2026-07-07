"""
Test per la configurabilità del modello OCR in GPT4oVisionProvider.

Il modello viene risolto così: override per-chiamata > settings.OCR_MODEL >
fallback "gpt-4o". Nessuna chiamata reale a OpenAI: il client è sempre mockato.
"""
import json
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from matches.services.vision_providers import GPT4oVisionProvider

FAKE_RESPONSE_JSON = json.dumps({
    "metadata": {"confidence": 0.9},
    "match_info": {"home_team": "Team A", "away_team": "Team B"},
})


def _mock_openai_response():
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=FAKE_RESPONSE_JSON))]
    response.usage = MagicMock(prompt_tokens=1200, completion_tokens=350)
    return response


class OCRModelConfigTest(SimpleTestCase):
    def setUp(self):
        fd, self.image_path = tempfile.mkstemp(suffix=".jpg")
        with os.fdopen(fd, "wb") as f:
            f.write(b"fake image bytes")
        self.addCleanup(os.remove, self.image_path)
        self.report = SimpleNamespace(
            id=999, file=SimpleNamespace(path=self.image_path)
        )

    def _run_extraction(self, model=None):
        with patch("openai.OpenAI") as mock_openai_class, \
             patch("matches.services.image_preprocessor.ImagePreprocessor.process",
                   return_value=self.image_path):
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            mock_client.chat.completions.create.return_value = _mock_openai_response()

            provider = GPT4oVisionProvider()
            if model is None:
                data, raw = provider.extract_data(self.report)
            else:
                data, raw = provider.extract_data(self.report, model=model)
            return data, mock_client.chat.completions.create

    def test_default_model_is_gpt4o(self):
        """Senza override e senza settings.OCR_MODEL, il modello resta gpt-4o."""
        data, mock_create = self._run_extraction()
        self.assertEqual(mock_create.call_args.kwargs["model"], "gpt-4o")
        self.assertEqual(data["metadata"]["model"], "gpt-4o")

    @override_settings(OCR_MODEL="gpt-4o-mini")
    def test_model_from_settings(self):
        """settings.OCR_MODEL definisce il default quando non c'è override."""
        data, mock_create = self._run_extraction()
        self.assertEqual(mock_create.call_args.kwargs["model"], "gpt-4o-mini")
        self.assertEqual(data["metadata"]["model"], "gpt-4o-mini")

    @override_settings(OCR_MODEL="gpt-4o-mini")
    def test_per_call_override_wins_over_settings(self):
        """L'override per-chiamata vince sia sul settings sia sul fallback."""
        data, mock_create = self._run_extraction(model="gpt-4.1")
        self.assertEqual(mock_create.call_args.kwargs["model"], "gpt-4.1")
        self.assertEqual(data["metadata"]["model"], "gpt-4.1")

    def test_token_usage_in_metadata(self):
        """Se la response OpenAI espone usage, finisce nei metadata."""
        data, _ = self._run_extraction()
        self.assertEqual(
            data["metadata"]["token_usage"],
            {"prompt_tokens": 1200, "completion_tokens": 350},
        )
