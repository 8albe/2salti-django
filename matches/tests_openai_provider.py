"""
Test per OpenAIVisionProvider (secondo lettore bench-only, syllabus §8.23).

Il client OpenAI è SEMPRE mockato: nessuna chiamata reale all'LLM, nessuna
dipendenza dalla rete. Coerente con la regola "mai chiamate reali all'LLM nei
test". Il provider NON è nel path di produzione (OCRService non lo conosce):
questi test coprono solo il seam bench (extract_data).
"""
import json
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock

from django.test import TestCase, override_settings

# Carica cv2 (via ImagePreprocessor) in modo pulito prima dei test, come nei
# test del provider Gemini.
import matches.services.image_preprocessor  # noqa: F401
from matches.services.vision_providers import (
    OpenAIVisionProvider,
    OCR_ALL_PROMPTS,
)


def _payload():
    """Payload JSON grezzo (pre-normalizzazione) in schema OCR v2."""
    return json.dumps({
        "metadata": {"confidence": 0.82, "confidence_fields": {"home_team": 0.9}},
        "match_info": {"home_team": "  POL. DELTA  ", "away_team": "VILLA YORK"},
        "scores": {"final_score": "10-8", "quarters": {"1": [3, 2], "2": [2, 2]}},
        "teams": {
            "home": {"players": [{"number": 1, "name": " Portiere "}]},
            "away": {"players": [{"number": 1, "name": "Opponente"}]},
        },
        "events": [{"type": "GOAL", "team": "home", "minute": 5}],
    })


def _response(content, finish_reason="stop", reasoning_tokens=None,
              prompt_tokens=1500, completion_tokens=400, refusal=None):
    """Costruisce un oggetto risposta OpenAI Chat Completions fittizio."""
    details = None
    if reasoning_tokens is not None:
        details = SimpleNamespace(reasoning_tokens=reasoning_tokens)
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        completion_tokens_details=details,
    )
    message = SimpleNamespace(content=content, refusal=refusal)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], usage=usage)


class OpenAIVisionProviderTest(TestCase):
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
        provider = OpenAIVisionProvider.__new__(OpenAIVisionProvider)
        provider.client = MagicMock()
        provider.client.chat.completions.create.return_value = response
        return provider

    def _create_kwargs(self, provider):
        return provider.client.chat.completions.create.call_args.kwargs

    def test_extract_data_returns_v2_schema(self):
        provider = self._make_provider(
            _response(_payload(), reasoning_tokens=1200)
        )
        sent = []
        data, raw = provider.extract_data(
            self.report, model="gpt-5", preprocess=False,
            prompt_version="v3_4", thinking_level="high",
            sent_image_callback=sent.append,
        )

        self.assertIsInstance(data, dict)
        self.assertIsInstance(raw, str)
        self.assertEqual(sent, [self.image_path])

        meta = data["metadata"]
        self.assertEqual(meta["provider"], "OpenAIVisionProvider-v1")
        self.assertEqual(meta["model"], "gpt-5")
        self.assertFalse(meta["preprocessed"])
        self.assertEqual(meta["schema_version"], "2.0")
        # reasoning_tokens -> thoughts_tokens (fatturati come output)
        self.assertEqual(meta["token_usage"], {
            "prompt_tokens": 1500, "completion_tokens": 400, "thoughts_tokens": 1200,
        })

        # Trimming e sezioni schema
        self.assertEqual(data["match_info"]["home_team"], "POL. DELTA")
        self.assertEqual(data["scores"]["final_score"], "10-8")
        self.assertEqual(data["teams"]["home"]["players"][0]["name"], "Portiere")
        self.assertEqual(len(data["events"]), 1)

        # La chiamata all'API: modello, JSON mode, tetto output, immagine data URI
        kwargs = self._create_kwargs(provider)
        self.assertEqual(kwargs["model"], "gpt-5")
        self.assertEqual(kwargs["response_format"], {"type": "json_object"})
        self.assertEqual(kwargs["max_completion_tokens"], 32000)
        user_content = kwargs["messages"][1]["content"]
        image_part = next(p for p in user_content if p["type"] == "image_url")
        self.assertTrue(image_part["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(image_part["image_url"]["detail"], "high")

    def test_v3_4_prompt_selected(self):
        provider = self._make_provider(_response(_payload()))
        provider.extract_data(
            self.report, model="gpt-5", preprocess=False, prompt_version="v3_4",
        )
        kwargs = self._create_kwargs(provider)
        self.assertEqual(kwargs["messages"][0]["role"], "system")
        self.assertEqual(kwargs["messages"][0]["content"], OCR_ALL_PROMPTS["v3_4"])

    def test_thinking_level_maps_to_reasoning_effort(self):
        provider = self._make_provider(_response(_payload()))
        provider.extract_data(
            self.report, model="gpt-5", preprocess=False, thinking_level="high",
        )
        self.assertEqual(self._create_kwargs(provider)["reasoning_effort"], "high")

    def test_no_thinking_level_no_reasoning_effort(self):
        """Default None: nessun reasoning_effort passato (default del modello)."""
        provider = self._make_provider(_response(_payload()))
        provider.extract_data(self.report, model="gpt-5", preprocess=False)
        self.assertNotIn("reasoning_effort", self._create_kwargs(provider))

    def test_thinking_budget_ignored(self):
        """thinking_budget è Gemini-specifico: ignorato, mai passato a OpenAI."""
        provider = self._make_provider(_response(_payload()))
        provider.extract_data(
            self.report, model="gpt-5", preprocess=False, thinking_budget=512,
        )
        kwargs = self._create_kwargs(provider)
        self.assertNotIn("reasoning_effort", kwargs)
        self.assertNotIn("thinking_budget", kwargs)

    def test_unknown_prompt_version_raises(self):
        provider = self._make_provider(_response(_payload()))
        with self.assertRaises(ValueError) as ctx:
            provider.extract_data(
                self.report, model="gpt-5", preprocess=False, prompt_version="v9_9",
            )
        self.assertIn("Prompt version sconosciuta", str(ctx.exception))

    def test_empty_content_raises(self):
        provider = self._make_provider(_response(None))
        with self.assertRaises(Exception) as ctx:
            provider.extract_data(self.report, model="gpt-5", preprocess=False)
        self.assertIn("OpenAI", str(ctx.exception))

    def test_refusal_raises_readable(self):
        provider = self._make_provider(_response(None, refusal="non posso"))
        with self.assertRaises(Exception) as ctx:
            provider.extract_data(self.report, model="gpt-5", preprocess=False)
        self.assertIn("refusal", str(ctx.exception).lower())

    def test_truncated_json_length_raises_readable(self):
        truncated = '{"metadata": {"confidence": 0.9}, "events": [{"type": "GOAL", "player_name": "ROS'
        provider = self._make_provider(_response(truncated, finish_reason="length"))
        with self.assertRaises(Exception) as ctx:
            provider.extract_data(self.report, model="gpt-5", preprocess=False)
        msg = str(ctx.exception)
        self.assertIn("troncato", msg)
        self.assertIn("OCR_MAX_OUTPUT_TOKENS", msg)
        self.assertNotIsInstance(ctx.exception, json.JSONDecodeError)

    def test_default_model_fallback(self):
        """Senza model esplicito e senza OPENAI_OCR_MODEL in settings: fallback gpt-5."""
        provider = self._make_provider(_response(_payload()))
        provider.extract_data(self.report, preprocess=False)
        self.assertEqual(self._create_kwargs(provider)["model"], "gpt-5")

    @override_settings(OCR_MAX_OUTPUT_TOKENS=12345)
    def test_max_output_tokens_configurable(self):
        provider = self._make_provider(_response(_payload()))
        provider.extract_data(self.report, model="gpt-5", preprocess=False)
        self.assertEqual(self._create_kwargs(provider)["max_completion_tokens"], 12345)
