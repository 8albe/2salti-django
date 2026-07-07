"""
Test per il management command ocr_bench.

Il provider è sempre mockato: nessuna chiamata reale a OpenAI nei test.
"""
import os
import tempfile
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import League, Society, Sport, Team
from matches.models import Match, MatchReport


def fake_extraction(model):
    """Estrazione fittizia in schema OCR v2, marcata col modello usato."""
    return {
        "metadata": {
            "confidence": 0.91,
            "model": model,
            "token_usage": {"prompt_tokens": 1000, "completion_tokens": 250},
        },
        "match_info": {"home_team": "POL. DELTA", "away_team": "VILLA YORK"},
        "scores": {
            "final_score": "10-8",
            "quarters": {"1": [3, 2], "2": [2, 2], "3": [3, 2], "4": [2, 2]},
        },
        "teams": {
            "home": {"players": [{"number": n, "name": f"Casa {n}"} for n in range(1, 8)]},
            "away": {"players": [{"number": n, "name": f"Ospite {n}"} for n in range(1, 8)]},
        },
        "events": [
            {"type": "GOAL", "team": "home", "minute": 5},
            {"type": "GOAL", "team": "away", "minute": 9},
        ],
    }


class OcrBenchCommandTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sport = Sport.objects.create(name="Pallanuoto")
        cls.league = League.objects.create(name="Serie A", sport=cls.sport)
        cls.soc_home = Society.objects.create(name="Soc Home", sport=cls.sport)
        cls.soc_away = Society.objects.create(name="Soc Away", sport=cls.sport)
        cls.home = Team.objects.create(society=cls.soc_home)
        cls.away = Team.objects.create(society=cls.soc_away)
        cls.match = Match.objects.create(
            league=cls.league,
            home_team=cls.home,
            away_team=cls.away,
            match_date=timezone.now(),
        )

    def setUp(self):
        fd, self.image_path = tempfile.mkstemp(suffix=".jpg")
        with os.fdopen(fd, "wb") as f:
            f.write(b"fake image bytes")
        self.addCleanup(os.remove, self.image_path)

    def _patch_provider(self):
        patcher = patch("matches.management.commands.ocr_bench.GPT4oVisionProvider")
        mock_class = patcher.start()
        self.addCleanup(patcher.stop)
        mock_provider = MagicMock()
        mock_class.return_value = mock_provider
        mock_provider.extract_data.side_effect = (
            lambda report, model=None: (fake_extraction(model), "raw")
        )
        return mock_provider

    def test_iterates_over_multiple_models(self):
        mock_provider = self._patch_provider()
        out = StringIO()
        call_command(
            "ocr_bench",
            "--image", self.image_path,
            "--models", "gpt-4o,gpt-4o-mini",
            stdout=out,
        )
        called_models = [
            c.kwargs["model"] for c in mock_provider.extract_data.call_args_list
        ]
        self.assertEqual(called_models, ["gpt-4o", "gpt-4o-mini"])
        output = out.getvalue()
        self.assertIn("gpt-4o", output)
        self.assertIn("gpt-4o-mini", output)
        self.assertIn("0.91", output)          # confidence
        self.assertIn("1000", output)          # prompt_tokens
        self.assertIn("250", output)           # completion_tokens

    @override_settings(OCR_MODEL="gpt-4o-mini")
    def test_default_model_comes_from_settings(self):
        mock_provider = self._patch_provider()
        out = StringIO()
        call_command("ocr_bench", "--image", self.image_path, stdout=out)
        self.assertEqual(mock_provider.extract_data.call_count, 1)
        self.assertEqual(
            mock_provider.extract_data.call_args.kwargs["model"], "gpt-4o-mini"
        )

    def test_missing_image_raises(self):
        self._patch_provider()
        with self.assertRaises(CommandError):
            call_command("ocr_bench", "--image", "/percorso/inesistente.jpg")

    def test_accuracy_with_validated_report(self):
        """Con --report-id e normalized_data, stampa l'accuracy per campo."""
        self._patch_provider()
        validated = fake_extraction("gpt-4o")
        validated["match_info"]["home_team"] = "ALTRA SQUADRA"  # 1 mismatch voluto
        report = MatchReport.objects.create(
            match=self.match,
            file=SimpleUploadedFile("report.jpg", b"img", content_type="image/jpeg"),
            status=MatchReport.Status.PUBLISHED,
            normalized_data=validated,
        )
        out = StringIO()
        call_command(
            "ocr_bench",
            "--image", self.image_path,
            "--models", "gpt-4o",
            "--report-id", str(report.pk),
            stdout=out,
        )
        output = out.getvalue()
        self.assertIn("Accuracy exact-match", output)
        self.assertIn("6/7", output)
        self.assertIn("mismatch: home_team", output)
        # Read-only: il report non deve essere toccato
        report.refresh_from_db()
        self.assertEqual(report.status, MatchReport.Status.PUBLISHED)
        self.assertEqual(report.normalized_data["match_info"]["home_team"], "ALTRA SQUADRA")

    def test_report_without_normalized_data_warns(self):
        self._patch_provider()
        report = MatchReport.objects.create(
            match=self.match,
            file=SimpleUploadedFile("report.jpg", b"img", content_type="image/jpeg"),
            status=MatchReport.Status.UPLOADED,
        )
        out = StringIO()
        call_command(
            "ocr_bench",
            "--image", self.image_path,
            "--models", "gpt-4o",
            "--report-id", str(report.pk),
            stdout=out,
        )
        self.assertIn("accuracy non calcolabile", out.getvalue())
        self.assertNotIn("Accuracy exact-match", out.getvalue())
