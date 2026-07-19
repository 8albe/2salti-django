"""
Test per il management command ocr_bench.

Il provider è sempre mockato: nessuna chiamata reale all'LLM nei test.
"""
import json
import os
import shutil
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

    def _patch_provider(self, extraction_factory=None):
        """Mocka GeminiVisionProvider (provider di default) sul simbolo del comando."""
        factory = extraction_factory or fake_extraction
        patcher = patch("matches.management.commands.ocr_bench.GeminiVisionProvider")
        mock_class = patcher.start()
        self.addCleanup(patcher.stop)
        mock_provider = MagicMock()
        mock_class.return_value = mock_provider

        def _fake_extract(report, model=None, preprocess=True, sent_image_callback=None):
            # Stesso contratto del provider reale: la callback riceve il path
            # dei byte inviati, prima della chiamata API.
            if sent_image_callback:
                sent_image_callback(report.file.path)
            return factory(model), "raw"

        mock_provider.extract_data.side_effect = _fake_extract
        return mock_provider

    def test_iterates_over_multiple_models(self):
        mock_provider = self._patch_provider()
        out = StringIO()
        call_command(
            "ocr_bench",
            "--image", self.image_path,
            "--models", "gemini-2.5-pro,gemini-2.5-flash",
            stdout=out,
        )
        called_models = [
            c.kwargs["model"] for c in mock_provider.extract_data.call_args_list
        ]
        self.assertEqual(called_models, ["gemini-2.5-pro", "gemini-2.5-flash"])
        output = out.getvalue()
        self.assertIn("gemini-2.5-pro", output)
        self.assertIn("gemini-2.5-flash", output)
        self.assertIn("0.91", output)          # confidence
        self.assertIn("1000", output)          # prompt_tokens
        self.assertIn("250", output)           # completion_tokens

    @override_settings(GEMINI_MODEL="gemini-2.5-flash")
    def test_default_model_comes_from_settings(self):
        mock_provider = self._patch_provider()
        out = StringIO()
        call_command("ocr_bench", "--image", self.image_path, stdout=out)
        self.assertEqual(mock_provider.extract_data.call_count, 1)
        self.assertEqual(
            mock_provider.extract_data.call_args.kwargs["model"], "gemini-2.5-flash"
        )

    def test_missing_image_raises(self):
        self._patch_provider()
        with self.assertRaises(CommandError):
            call_command("ocr_bench", "--image", "/percorso/inesistente.jpg")

    def test_accuracy_with_validated_report(self):
        """Con --report-id e normalized_data, stampa l'accuracy per campo."""
        self._patch_provider()
        validated = fake_extraction("gemini-2.5-pro")
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
            "--models", "gemini-2.5-pro",
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

    def test_show_prints_extracted_fields_per_model(self):
        """--show stampa un blocco per modello con i campi chiave estratti."""
        self._patch_provider()
        out = StringIO()
        call_command(
            "ocr_bench",
            "--image", self.image_path,
            "--models", "gemini-2.5-pro,gemini-2.5-flash",
            "--show",
            stdout=out,
        )
        output = out.getvalue()
        self.assertIn("=== gemini-2.5-pro ===", output)
        self.assertIn("=== gemini-2.5-flash ===", output)
        self.assertIn("POL. DELTA", output)
        self.assertIn("VILLA YORK", output)
        self.assertIn("10-8", output)
        self.assertIn("quarti (4)", output)
        self.assertIn("roster casa (7)", output)
        self.assertIn("roster ospiti (7)", output)
        self.assertIn("Casa 1", output)
        self.assertIn("eventi (2)", output)
        self.assertIn("GOAL", output)

    def test_show_marks_missing_fields(self):
        """--show segnala esplicitamente i campi assenti nell'estrazione."""
        self._patch_provider(
            extraction_factory=lambda model: {
                "metadata": {"confidence": 0.50, "model": model},
                "match_info": {"home_team": "POL. DELTA"},  # away_team mancante
            }
        )
        out = StringIO()
        call_command(
            "ocr_bench",
            "--image", self.image_path,
            "--models", "gemini-2.5-pro",
            "--show",
            stdout=out,
        )
        output = out.getvalue()
        self.assertIn("away_team:   — assente", output)
        self.assertIn("final_score: — assente", output)
        self.assertIn("quarti: — assente", output)
        self.assertIn("roster casa: — assente", output)
        self.assertIn("roster ospiti: — assente", output)
        self.assertIn("eventi: — assente", output)

    def test_save_dir_writes_json_per_model(self):
        """--save-dir scrive un file JSON completo per ogni modello."""
        self._patch_provider()
        save_dir = os.path.join(tempfile.mkdtemp(), "bench_out")  # dir non esistente
        self.addCleanup(shutil.rmtree, os.path.dirname(save_dir))
        out = StringIO()
        call_command(
            "ocr_bench",
            "--image", self.image_path,
            "--models", "gemini-2.5-pro,gemini-2.5-flash",
            "--save-dir", save_dir,
            stdout=out,
        )
        files = sorted(os.listdir(save_dir))
        self.assertEqual(len(files), 2)
        saved_models = set()
        for fname in files:
            self.assertTrue(fname.startswith("ocr_bench_gemini-"))
            self.assertTrue(fname.endswith(".json"))
            with open(os.path.join(save_dir, fname), encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["match_info"]["home_team"], "POL. DELTA")
            saved_models.add(data["metadata"]["model"])
        self.assertEqual(saved_models, {"gemini-2.5-pro", "gemini-2.5-flash"})
        self.assertIn("Salvato:", out.getvalue())

    def test_without_new_flags_no_blocks_and_no_files(self):
        """Senza --show/--save-dir l'output resta la sola tabella di oggi."""
        self._patch_provider()
        out = StringIO()
        call_command(
            "ocr_bench",
            "--image", self.image_path,
            "--models", "gemini-2.5-pro",
            stdout=out,
        )
        output = out.getvalue()
        self.assertNotIn("=== gemini-2.5-pro ===", output)
        self.assertNotIn("Salvato:", output)
        self.assertIn("confidence", output)

    def test_default_call_omits_new_kwargs(self):
        """Senza --dump-sent-image/--no-preprocess la chiamata al provider è identica a prima."""
        mock_provider = self._patch_provider()
        call_command(
            "ocr_bench", "--image", self.image_path, "--models", "gemini-2.5-pro",
            stdout=StringIO(),
        )
        kwargs = mock_provider.extract_data.call_args.kwargs
        self.assertEqual(set(kwargs), {"model"})

    def test_no_preprocess_propagates_flag(self):
        """--no-preprocess passa preprocess=False al provider."""
        mock_provider = self._patch_provider()
        call_command(
            "ocr_bench", "--image", self.image_path, "--models", "gemini-2.5-pro",
            "--no-preprocess",
            stdout=StringIO(),
        )
        kwargs = mock_provider.extract_data.call_args.kwargs
        self.assertIs(kwargs.get("preprocess"), False)

    def test_dump_sent_image_writes_file_per_model(self):
        """--dump-sent-image salva un file per modello con i byte inviati."""
        self._patch_provider()
        dump_dir = os.path.join(tempfile.mkdtemp(), "sent_out")  # dir non esistente
        self.addCleanup(shutil.rmtree, os.path.dirname(dump_dir))
        out = StringIO()
        call_command(
            "ocr_bench",
            "--image", self.image_path,
            "--models", "gemini-2.5-pro,gemini-2.5-flash",
            "--dump-sent-image", dump_dir,
            stdout=out,
        )
        files = sorted(os.listdir(dump_dir))
        self.assertEqual(len(files), 2)
        prefixes = {f.rsplit("_", 2)[0] for f in files}
        self.assertEqual(
            prefixes, {"ocr_bench_sent_gemini-2.5-pro", "ocr_bench_sent_gemini-2.5-flash"}
        )
        for fname in files:
            self.assertTrue(fname.endswith(".jpg"))
            with open(os.path.join(dump_dir, fname), "rb") as f:
                self.assertEqual(f.read(), b"fake image bytes")
        self.assertIn("Immagine inviata salvata:", out.getvalue())

    def test_dump_sent_image_works_with_no_preprocess(self):
        """I due flag insieme: dump dei byte grezzi inviati senza preprocessing."""
        mock_provider = self._patch_provider()
        dump_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, dump_dir)
        call_command(
            "ocr_bench",
            "--image", self.image_path,
            "--models", "gemini-2.5-pro",
            "--dump-sent-image", dump_dir,
            "--no-preprocess",
            stdout=StringIO(),
        )
        kwargs = mock_provider.extract_data.call_args.kwargs
        self.assertIs(kwargs.get("preprocess"), False)
        files = os.listdir(dump_dir)
        self.assertEqual(len(files), 1)
        with open(os.path.join(dump_dir, files[0]), "rb") as f:
            self.assertEqual(f.read(), b"fake image bytes")

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
            "--models", "gemini-2.5-pro",
            "--report-id", str(report.pk),
            stdout=out,
        )
        self.assertIn("accuracy non calcolabile", out.getvalue())
        self.assertNotIn("Accuracy exact-match", out.getvalue())

    def test_provider_gemini_explicit_flag(self):
        """--provider gemini è esplicitabile e stampato in output (seam estendibile)."""
        mock_provider = self._patch_provider()
        out = StringIO()
        call_command(
            "ocr_bench",
            "--image", self.image_path,
            "--provider", "gemini",
            "--models", "gemini-2.5-pro,gemini-2.5-flash",
            "--show",
            stdout=out,
        )
        output = out.getvalue()
        self.assertIn("Provider: gemini", output)
        self.assertIn("=== gemini-2.5-pro ===", output)
        self.assertIn("=== gemini-2.5-flash ===", output)
        called_models = [
            c.kwargs["model"] for c in mock_provider.extract_data.call_args_list
        ]
        self.assertEqual(called_models, ["gemini-2.5-pro", "gemini-2.5-flash"])

    def test_default_provider_is_gemini(self):
        """Senza --provider si usa GeminiVisionProvider (provider unico di default)."""
        mock_provider = self._patch_provider()
        out = StringIO()
        call_command(
            "ocr_bench", "--image", self.image_path, "--models", "gemini-2.5-pro",
            stdout=out,
        )
        self.assertEqual(mock_provider.extract_data.call_count, 1)
        self.assertIn("Provider: gemini", out.getvalue())
