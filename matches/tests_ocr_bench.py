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

        def _fake_extract(report, model=None, preprocess=True, sent_image_callback=None,
                          prompt_version=None):
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

    def test_prompt_version_v3_propagates_to_provider(self):
        """--prompt-version v3 passa prompt_version='v3' al provider; v2 resta implicito."""
        mock_provider = self._patch_provider()
        call_command(
            "ocr_bench", "--image", self.image_path, "--models", "gemini-2.5-pro",
            "--prompt-version", "v3",
            stdout=StringIO(),
        )
        kwargs = mock_provider.extract_data.call_args.kwargs
        self.assertEqual(kwargs.get("prompt_version"), "v3")

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

    def test_image_required_without_gold_mode(self):
        """Senza --image e senza --gold-case/--gold-all il comando rifiuta."""
        self._patch_provider()
        with self.assertRaises(CommandError):
            call_command("ocr_bench", "--models", "gemini-2.5-pro")


def gold_truth_extraction(model):
    """Estrazione che coincide con la truth del caso gold di test."""
    return {
        "metadata": {
            "confidence": 0.91,
            "confidence_fields": {
                "final_score": 1.0,
                "quarters": 0.9,
                "home_team": 1.0,
                "away_team": 0.5,
            },
        },
        "match_info": {
            "home_team": "CASA SUL FOGLIO",
            "away_team": "OSPITI SUL FOGLIO",
            "date": "2026-01-01",
        },
        "scores": {
            "final_score": "10-8",
            "quarters": {"1": [3, 2], "2": [2, 2], "3": [3, 2], "4": [2, 2]},
        },
        "teams": {
            "home": {"players": [{"number": 1, "name": "Uno"}]},
            "away": {"players": []},
        },
        "events": [{"type": "GOAL", "team": "home"}],
    }


class OcrBenchGoldModeTest(TestCase):
    """Modalità --gold-case/--gold-all: confronto con la truth, provider sempre mockato."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.cases_dir = os.path.join(self.tmp, "cases")
        self.out_dir = os.path.join(self.tmp, "out")
        self.media_root = os.path.join(self.tmp, "media")
        os.makedirs(self.cases_dir)
        override = override_settings(MEDIA_ROOT=self.media_root)
        override.enable()
        self.addCleanup(override.disable)
        self.report = MatchReport.objects.create(
            file=SimpleUploadedFile("referto_gold.jpg", b"gold image", content_type="image/jpeg"),
            status=MatchReport.Status.NEEDS_REVIEW,
        )
        fd, self.loose_image = tempfile.mkstemp(suffix=".jpg", dir=self.tmp)
        with os.fdopen(fd, "wb") as f:
            f.write(b"loose image bytes")

    def _write_case(self, case_id="2026-01-01_test-home_vs_test-away", report_pk=None,
                    extra=None):
        case = {
            "case_id": case_id,
            "verified_by": "Test Umano",
            "verified_at": "2026-01-02",
            "match": {
                "db_match_pk": None,
                "date": "2026-01-01",
                "home_team": {"db_team_name": "Casa DB", "name_on_paper": "CASA SUL FOGLIO"},
                "away_team": {"db_team_name": "Ospiti DB", "name_on_paper": "OSPITI SUL FOGLIO"},
            },
            "truth": {
                "scores": {
                    "final_score": "10-8",
                    "quarters": {"1": [3, 2], "2": [2, 2], "3": [3, 2], "4": [2, 2]},
                }
            },
            "not_verified": ["roster casa e trasferta", "eventi"],
            "extractions": (
                [{"provider": "vecchia", "db_report_pk": report_pk}] if report_pk else []
            ),
        }
        if extra:
            case.update(extra)
        path = os.path.join(self.cases_dir, f"{case_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(case, f)
        return case_id

    def _patch_provider(self, extraction_factory=gold_truth_extraction):
        patcher = patch("matches.management.commands.ocr_bench.GeminiVisionProvider")
        mock_class = patcher.start()
        self.addCleanup(patcher.stop)
        mock_provider = MagicMock()
        mock_class.return_value = mock_provider

        def _fake_extract(report, model=None, preprocess=True, sent_image_callback=None,
                          prompt_version=None):
            return extraction_factory(model), "raw"

        mock_provider.extract_data.side_effect = _fake_extract
        return mock_provider

    def _call_gold(self, *extra_args, factory=gold_truth_extraction):
        self._patch_provider(factory)
        out = StringIO()
        call_command(
            "ocr_bench",
            "--models", "gemini-2.5-pro",
            "--cases-dir", self.cases_dir,
            "--out-dir", self.out_dir,
            *extra_args,
            stdout=out,
        )
        return out.getvalue()

    def _proposal(self):
        files = os.listdir(self.out_dir)
        self.assertEqual(len(files), 1)
        with open(os.path.join(self.out_dir, files[0]), encoding="utf-8") as f:
            return files[0], json.load(f)

    def test_gold_case_all_correct(self):
        """Estrazione identica alla truth: tutti i campi correct, proposta su file."""
        case_id = self._write_case(report_pk=self.report.pk)
        output = self._call_gold("--gold-case", case_id)
        self.assertIn(f"Caso gold: {case_id}", output)
        self.assertIn("final_score_home", output)
        self.assertIn("quarter_4_away", output)
        self.assertIn("13 correct, 0 wrong, 0 null", output)
        self.assertNotIn("INVERSIONE RILEVATA", output)
        fname, proposal = self._proposal()
        self.assertTrue(fname.startswith(case_id))
        self.assertEqual(proposal["db_report_pk"], self.report.pk)
        self.assertEqual(proposal["verdict"]["final_score_home"], "correct")
        self.assertEqual(proposal["verdict"]["quarter_1_away"], "correct")
        # ciò che sta in not_verified resta fuori dal confronto per costruzione
        self.assertEqual(proposal["verdict"]["roster"], "unverified")
        self.assertEqual(proposal["verdict"]["events"], "unverified")
        self.assertFalse(proposal["inversion_check"]["any"])
        # metadati di run: senza questi il bench non è ripetibile
        run = proposal["bench_run"]
        self.assertEqual(run["model"], "gemini-2.5-pro")
        self.assertIn("OCR_SYSTEM_PROMPT_V2@sha256:", run["prompt_version"])
        self.assertTrue(run["preprocessing"])
        self.assertTrue(run["timestamp"])
        self.assertEqual(run["image_resolved_from"], f"db_report_pk={self.report.pk}")

    def test_gold_case_prompt_v3_recorded_in_proposal(self):
        """Con --prompt-version v3 la proposta registra simbolo e hash del prompt V3."""
        case_id = self._write_case(report_pk=self.report.pk)
        output = self._call_gold("--gold-case", case_id, "--prompt-version", "v3")
        self.assertIn("OCR_SYSTEM_PROMPT_V3@sha256:", output)
        _fname, proposal = self._proposal()
        self.assertIn(
            "OCR_SYSTEM_PROMPT_V3@sha256:", proposal["bench_run"]["prompt_version"]
        )
        self.assertNotIn("OCR_SYSTEM_PROMPT_V2", proposal["bench_run"]["prompt_version"])

    def test_gold_case_wrong_and_null_counted_separately(self):
        """wrong e null distinti: l'astensione dichiarata non è un errore."""
        def factory(model):
            data = gold_truth_extraction(model)
            data["scores"]["final_score"] = "10-9"          # away wrong, home correct
            data["scores"]["quarters"]["2"] = [None, 2]      # q2 home null
            data["scores"]["quarters"]["3"] = [4, 2]         # q3 home wrong
            data["match_info"]["away_team"] = None           # nome away null
            return data

        case_id = self._write_case(report_pk=self.report.pk)
        output = self._call_gold("--gold-case", case_id, factory=factory)
        self.assertIn("9 correct, 2 wrong, 2 null", output)
        _, proposal = self._proposal()
        v = proposal["verdict"]
        self.assertEqual(v["final_score_home"], "correct")
        self.assertEqual(v["final_score_away"], "wrong")
        self.assertEqual(v["quarter_2_home"], "null")
        self.assertEqual(v["quarter_2_away"], "correct")
        self.assertEqual(v["quarter_3_home"], "wrong")
        self.assertEqual(v["away_team_name"], "null")
        # confidence auto-dichiarata accostata al verdetto (curva di calibrazione)
        self.assertEqual(proposal["comparison"]["final_score_away"]["confidence"], 1.0)
        self.assertEqual(proposal["comparison"]["quarter_3_home"]["confidence"], 0.9)

    def test_gold_case_team_names_compared_with_name_on_paper(self):
        """Il confronto nomi usa name_on_paper, non il nome a DB; la punteggiatura non conta."""
        def factory(model):
            data = gold_truth_extraction(model)
            data["match_info"]["home_team"] = "Casa. Sul-Foglio"   # uguale normalizzato
            data["match_info"]["away_team"] = "Ospiti DB"          # nome a DB: per l'OCR è wrong
            return data

        case_id = self._write_case(report_pk=self.report.pk)
        self._call_gold("--gold-case", case_id, factory=factory)
        _, proposal = self._proposal()
        self.assertEqual(proposal["verdict"]["home_team_name"], "correct")
        self.assertEqual(proposal["verdict"]["away_team_name"], "wrong")

    def test_gold_case_long_values_not_truncated_in_table(self):
        """Nomi più lunghi della larghezza di colonna storica (18) non vanno mai troncati.

        Regressione: la tabella usava una larghezza fissa di 18 caratteri.
        Python non tronca mai una stringa più lunga del solo campo width (solo
        precision lo fa), quindi la stampa era già completa — ma un valore più
        largo della colonna sbandava l'allineamento delle colonne successive,
        al punto da poter leggersi come troncato. Le colonne ora si
        dimensionano sul contenuto: qui forziamo un nome ben oltre i 18
        caratteri storici e verifichiamo che compaia integro in output.
        """
        long_paper_name = "BELLATOR FROSINONE MOLTO PIU LUNGO DI DICIOTTO CARATTERI"

        def factory(model):
            data = gold_truth_extraction(model)
            data["match_info"]["home_team"] = long_paper_name
            return data

        case_id = self._write_case(
            report_pk=self.report.pk,
            extra={
                "match": {
                    "db_match_pk": None,
                    "date": "2026-01-01",
                    "home_team": {
                        "db_team_name": "Casa DB",
                        "name_on_paper": long_paper_name,
                    },
                    "away_team": {"db_team_name": "Ospiti DB", "name_on_paper": "OSPITI SUL FOGLIO"},
                }
            },
        )
        output = self._call_gold("--gold-case", case_id, factory=factory)
        self.assertGreater(len(long_paper_name), 18)
        self.assertIn(long_paper_name, output)
        # ogni riga della tabella deve contenere il valore intero e non un
        # prefisso di esso: un troncamento a 18 caratteri produrrebbe
        # "BELLATOR FROSINONE" (spazio compreso, 18 char) senza il resto.
        self.assertNotIn(long_paper_name[:18] + "\n", output)
        _, proposal = self._proposal()
        self.assertEqual(proposal["comparison"]["home_team_name"]["truth"], long_paper_name)
        self.assertEqual(proposal["comparison"]["home_team_name"]["extracted"], long_paper_name)

    def test_gold_case_detects_home_away_inversion(self):
        """Valori giusti attribuiti alla squadra sbagliata: la classe di errore del match 2."""
        def factory(model):
            data = gold_truth_extraction(model)
            data["match_info"]["home_team"] = "OSPITI SUL FOGLIO"
            data["match_info"]["away_team"] = "CASA SUL FOGLIO"
            data["scores"]["final_score"] = "8-10"
            data["scores"]["quarters"] = {
                "1": [2, 3], "2": [2, 2], "3": [2, 3], "4": [2, 2]
            }
            return data

        case_id = self._write_case(report_pk=self.report.pk)
        output = self._call_gold("--gold-case", case_id, factory=factory)
        self.assertIn("INVERSIONE RILEVATA", output)
        _, proposal = self._proposal()
        inv = proposal["inversion_check"]
        self.assertTrue(inv["final_score"])
        self.assertTrue(inv["team_names"])
        self.assertTrue(inv["quarters"]["1"])
        self.assertTrue(inv["quarters"]["3"])
        self.assertIsNone(inv["quarters"]["2"])  # truth simmetrica: non computabile
        self.assertTrue(inv["any"])

    def test_gold_case_is_read_only_and_never_touches_cases(self):
        """Il report a DB e il file del caso restano identici byte per byte."""
        case_id = self._write_case(report_pk=self.report.pk)
        case_path = os.path.join(self.cases_dir, f"{case_id}.json")
        with open(case_path, "rb") as f:
            case_before = f.read()
        self._call_gold("--gold-case", case_id)
        with open(case_path, "rb") as f:
            self.assertEqual(f.read(), case_before)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, MatchReport.Status.NEEDS_REVIEW)
        self.assertEqual(self.report.normalized_data, {})

    def test_gold_case_explicit_image_for_case_without_report(self):
        """--image copre i casi senza report a DB (immagine fuori da media)."""
        case_id = self._write_case()  # nessun db_report_pk
        output = self._call_gold("--gold-case", case_id, "--image", self.loose_image)
        self.assertIn("13 correct", output)
        _, proposal = self._proposal()
        self.assertIsNone(proposal["db_report_pk"])
        self.assertEqual(proposal["bench_run"]["image_resolved_from"], "--image")

    def test_gold_case_without_resolvable_image_raises(self):
        """Senza report a DB e senza --image il singolo caso è un errore esplicito."""
        case_id = self._write_case()
        self._patch_provider()
        with self.assertRaises(CommandError):
            call_command(
                "ocr_bench", "--gold-case", case_id,
                "--cases-dir", self.cases_dir, "--out-dir", self.out_dir,
                "--models", "gemini-2.5-pro", stdout=StringIO(),
            )

    def test_gold_all_processes_resolvable_and_skips_missing(self):
        """--gold-all: elabora i casi con immagine, salta gli altri con avviso."""
        ok_case = self._write_case(
            case_id="2026-01-01_caso-ok_vs_x", report_pk=self.report.pk
        )
        missing_case = self._write_case(case_id="2026-02-02_caso-senza-foto_vs_y")
        output = self._call_gold("--gold-all")
        self.assertIn(f"Caso gold: {ok_case}", output)
        self.assertIn(f"'{missing_case}' SALTATO", output)
        self.assertIn("Casi saltati:", output)
        fname, _ = self._proposal()  # una sola proposta: quella del caso ok
        self.assertTrue(fname.startswith(ok_case))

    def test_gold_flag_combinations_rejected(self):
        """--gold-case + --gold-all, --gold-all + --image, gold + --report-id: tutti rifiutati."""
        case_id = self._write_case(report_pk=self.report.pk)
        self._patch_provider()
        base = ["--cases-dir", self.cases_dir, "--out-dir", self.out_dir,
                "--models", "gemini-2.5-pro"]
        with self.assertRaises(CommandError):
            call_command("ocr_bench", "--gold-case", case_id, "--gold-all", *base,
                         stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("ocr_bench", "--gold-all", "--image", self.loose_image, *base,
                         stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("ocr_bench", "--gold-case", case_id, "--report-id",
                         str(self.report.pk), *base, stdout=StringIO())

    def test_gold_case_unknown_id_lists_available(self):
        self._write_case(case_id="2026-01-01_esiste_vs_x", report_pk=self.report.pk)
        self._patch_provider()
        with self.assertRaises(CommandError) as ctx:
            call_command(
                "ocr_bench", "--gold-case", "non-esiste",
                "--cases-dir", self.cases_dir, "--out-dir", self.out_dir,
                stdout=StringIO(),
            )
        self.assertIn("2026-01-01_esiste_vs_x", str(ctx.exception))

    # --- --repeat N: N estrazioni indipendenti sullo stesso caso/modello ---
    #
    # L'estrazione non è deterministica (comportamento reale: due chiamate
    # Gemini sullo stesso referto hanno prodotto "BELLATOR FROSINONE" e
    # "BELLATOR FROSINO", entrambe confidence 1.0). I factory qui restituiscono
    # valori DIVERSI a chiamate successive, a differenza dei test sopra dove
    # ogni test fissa un'unica estrazione costante.

    def test_repeat_requires_gold_mode(self):
        """--repeat > 1 senza --gold-case/--gold-all è un errore esplicito."""
        self._patch_provider()
        with self.assertRaises(CommandError):
            call_command(
                "ocr_bench", "--image", self.loose_image, "--repeat", "2",
                stdout=StringIO(),
            )

    def test_repeat_must_be_at_least_one(self):
        with self.assertRaises(CommandError):
            call_command(
                "ocr_bench", "--gold-case", "qualunque", "--repeat", "0",
                stdout=StringIO(),
            )

    def test_repeat_one_is_default_and_unchanged(self):
        """--repeat 1 (o l'assenza del flag) produce la proposta a estrazione singola."""
        case_id = self._write_case(report_pk=self.report.pk)
        output = self._call_gold("--gold-case", case_id)
        self.assertNotIn("Ripetizione", output)
        _, proposal = self._proposal()
        self.assertNotIn("repeats", proposal)
        self.assertNotIn("aggregate", proposal)

    def test_repeat_reports_stability_instability_and_confidence_range(self):
        """Campo stabile-corretto, stabile-ma-sbagliato e ambiguo, tutti nello stesso run."""
        calls = []

        def factory(model):
            data = gold_truth_extraction(model)
            i = len(calls) + 1
            calls.append(i)
            # ambiguo: pareggio 2-2 fra un valore corretto e uno sbagliato
            data["match_info"]["home_team"] = (
                "CASA SUL FOGLIO" if i % 2 else "CASA SUL FOGLIO BIS"
            )
            # stabile ma sbagliato: sempre lo stesso valore, sempre diverso dalla truth
            data["match_info"]["away_team"] = "NOME SBAGLIATO SEMPRE"
            data["metadata"]["confidence_fields"]["away_team"] = 0.5 + i * 0.1
            return data

        case_id = self._write_case(report_pk=self.report.pk)
        output = self._call_gold("--gold-case", case_id, "--repeat", "4", factory=factory)

        self.assertIn("Ripetizione 1/4", output)
        self.assertIn("Ripetizione 4/4", output)
        self.assertIn("instabile", output)
        self.assertIn("SENZA MAGGIORANZA", output)
        self.assertIn("STABILE MA SBAGLIATO", output)
        self.assertIn("AMBIGUO", output)

        _, proposal = self._proposal()
        self.assertEqual(proposal["bench_run"]["repeat"], 4)
        self.assertEqual(len(proposal["repeats"]), 4)

        home = proposal["aggregate"]["home_team_name"]
        self.assertEqual(home["stability"], "instabile")
        self.assertFalse(home["has_majority"])
        self.assertEqual(home["verdict"], "ambiguo")
        self.assertEqual(len(home["distinct_values"]), 2)
        self.assertEqual(sum(v["count"] for v in home["distinct_values"]), 4)
        tied = {t["value"]: t["verdict"] for t in home["tied_values"]}
        self.assertEqual(tied, {"CASA SUL FOGLIO": "correct", "CASA SUL FOGLIO BIS": "wrong"})
        self.assertIn(home["tie_break_hint"], tied)

        away = proposal["aggregate"]["away_team_name"]
        self.assertEqual(away["stability"], "stabile")
        self.assertTrue(away["has_majority"])
        self.assertEqual(away["verdict"], "wrong")
        self.assertIsNone(away["tied_values"])
        self.assertTrue(away["stable_and_wrong"])
        self.assertAlmostEqual(away["confidence_mean"], (0.6 + 0.7 + 0.8 + 0.9) / 4)
        self.assertEqual(away["confidence_min"], 0.6)
        self.assertEqual(away["confidence_max"], 0.9)

        # date, final_score e gli 8 quarti restano invariati e corretti a ogni
        # ripetizione: 11 campi stabili-corretti su 13 confrontati.
        self.assertEqual(proposal["summary"], {
            "stable_correct": 11,
            "stable_wrong": 1,
            "stable_null": 0,
            "instabile": 0,
            "ambiguo": 1,
        })

    def test_repeat_tie_between_correct_and_wrong_is_ambiguous_not_tie_broken(self):
        """Pareggio 2-2 fra un valore corretto e uno sbagliato: esito 'ambiguo', non un
        tie-break silenzioso per ordine di arrivo (il bug osservato sul caso Bellator:
        FRUSINO x2 corretto / FROSINONE x2 sbagliato stampava "correct" solo perché
        FRUSINO era arrivato per primo)."""
        calls = []

        def factory(model):
            data = gold_truth_extraction(model)
            i = len(calls) + 1
            calls.append(i)
            data["match_info"]["home_team"] = (
                "CASA SUL FOGLIO" if i in (1, 2) else "CASA SBAGLIATA"
            )
            return data

        case_id = self._write_case(report_pk=self.report.pk)
        output = self._call_gold("--gold-case", case_id, "--repeat", "4", factory=factory)
        self.assertIn("AMBIGUO", output)

        _, proposal = self._proposal()
        home = proposal["aggregate"]["home_team_name"]
        self.assertEqual(home["verdict"], "ambiguo")
        self.assertFalse(home["has_majority"])
        self.assertEqual(home["stability"], "instabile")
        tied = {t["value"]: t["verdict"] for t in home["tied_values"]}
        self.assertEqual(tied, {"CASA SUL FOGLIO": "correct", "CASA SBAGLIATA": "wrong"})

        self.assertEqual(proposal["summary"]["ambiguo"], 1)
        self.assertEqual(proposal["summary"]["stable_correct"], 12)
        self.assertEqual(proposal["summary"]["stable_wrong"], 0)
        self.assertEqual(proposal["summary"]["instabile"], 0)

    def test_repeat_tie_between_two_wrong_values_is_ambiguous(self):
        """Pareggio 2-2 fra due valori entrambi sbagliati: resta 'ambiguo', mai promosso
        a 'wrong' e mai a 'correct' — nessuno dei due coincide con la truth."""
        calls = []

        def factory(model):
            data = gold_truth_extraction(model)
            i = len(calls) + 1
            calls.append(i)
            data["match_info"]["away_team"] = (
                "OSPITI SBAGLIATI A" if i in (1, 3) else "OSPITI SBAGLIATI B"
            )
            return data

        case_id = self._write_case(report_pk=self.report.pk)
        self._call_gold("--gold-case", case_id, "--repeat", "4", factory=factory)

        _, proposal = self._proposal()
        away = proposal["aggregate"]["away_team_name"]
        self.assertEqual(away["verdict"], "ambiguo")
        self.assertFalse(away["has_majority"])
        tied_verdicts = {t["verdict"] for t in away["tied_values"]}
        self.assertEqual(tied_verdicts, {"wrong"})

        self.assertEqual(proposal["summary"]["ambiguo"], 1)
        self.assertEqual(proposal["summary"]["stable_wrong"], 0)
        self.assertEqual(proposal["summary"]["stable_correct"], 12)

    def test_repeat_strict_majority_resolves_normally_not_ambiguous(self):
        """3 chiamate su 4 concordi: la maggioranza stretta esiste (3 > 4/2), l'esito
        resta correct/wrong come prima — comportamento invariato per i casi con una
        vera maggioranza, solo il pareggio senza maggioranza diventa 'ambiguo'."""
        calls = []

        def factory(model):
            data = gold_truth_extraction(model)
            i = len(calls) + 1
            calls.append(i)
            data["match_info"]["home_team"] = "CASA SUL FOGLIO" if i != 4 else "CASA RARA"
            return data

        case_id = self._write_case(report_pk=self.report.pk)
        output = self._call_gold("--gold-case", case_id, "--repeat", "4", factory=factory)
        self.assertNotIn("AMBIGUO", output)
        self.assertNotIn("SENZA MAGGIORANZA", output)

        _, proposal = self._proposal()
        home = proposal["aggregate"]["home_team_name"]
        self.assertEqual(home["stability"], "instabile")
        self.assertTrue(home["has_majority"])
        self.assertEqual(home["verdict"], "correct")
        self.assertIsNone(home["tied_values"])
        self.assertIsNone(home["tie_break_hint"])

        self.assertEqual(proposal["summary"]["instabile"], 1)
        self.assertEqual(proposal["summary"]["ambiguo"], 0)

    def test_repeat_proposal_keeps_every_extraction_not_just_the_last(self):
        """repeats[] contiene tutte le N estrazioni, non solo l'ultima."""
        calls = []

        def factory(model):
            data = gold_truth_extraction(model)
            i = len(calls) + 1
            calls.append(i)
            data["scores"]["final_score"] = f"10-{7 + i}"  # 10-8, 10-9, 10-10: tutte diverse
            return data

        case_id = self._write_case(report_pk=self.report.pk)
        self._call_gold("--gold-case", case_id, "--repeat", "3", factory=factory)
        _, proposal = self._proposal()

        self.assertEqual(len(proposal["repeats"]), 3)
        away_scores = [
            r["extracted"]["scores"]["final_score"] for r in proposal["repeats"]
        ]
        self.assertEqual(away_scores, ["10-8", "10-9", "10-10"])
        self.assertEqual(proposal["aggregate"]["final_score_away"]["stability"], "instabile")

    def test_repeat_proposal_persists_extraction_warnings(self):
        """Ogni ripetizione porta i suoi extraction_warnings (segnale somma!=finale misurabile)."""
        def factory(model):
            data = gold_truth_extraction(model)
            data["metadata"]["extraction_warnings"] = [
                "somma parziali (5) diversa dal finale casa (4)"
            ]
            return data

        case_id = self._write_case(report_pk=self.report.pk)
        self._call_gold("--gold-case", case_id, "--repeat", "2", factory=factory)
        _, proposal = self._proposal()
        self.assertEqual(len(proposal["repeats"]), 2)
        for rep in proposal["repeats"]:
            self.assertEqual(
                rep["extraction_warnings"],
                ["somma parziali (5) diversa dal finale casa (4)"],
            )

    def test_single_proposal_persists_extraction_warnings(self):
        """Anche la proposta a estrazione singola porta gli extraction_warnings."""
        def factory(model):
            data = gold_truth_extraction(model)
            data["metadata"]["extraction_warnings"] = ["nome away parzialmente leggibile"]
            return data

        case_id = self._write_case(report_pk=self.report.pk)
        self._call_gold("--gold-case", case_id, factory=factory)
        _, proposal = self._proposal()
        self.assertEqual(
            proposal["extraction_warnings"], ["nome away parzialmente leggibile"]
        )

    def test_repeat_all_calls_failing_skips_model_without_crashing(self):
        """Se ogni ripetizione fallisce, il modello viene saltato (non un traceback)."""
        patcher = patch("matches.management.commands.ocr_bench.GeminiVisionProvider")
        mock_class = patcher.start()
        self.addCleanup(patcher.stop)
        mock_provider = MagicMock()
        mock_class.return_value = mock_provider
        mock_provider.extract_data.side_effect = RuntimeError("Gemini API Timeout")

        case_id = self._write_case(report_pk=self.report.pk)
        out = StringIO()
        call_command(
            "ocr_bench", "--gold-case", case_id, "--repeat", "3",
            "--models", "gemini-2.5-pro",
            "--cases-dir", self.cases_dir, "--out-dir", self.out_dir,
            stdout=out,
        )
        self.assertIn("nessuna estrazione riuscita su 3 tentativi", out.getvalue())
        self.assertEqual(os.listdir(self.out_dir), [])


class OcrPromptV3ContentTest(TestCase):
    """Guardrail sul contenuto dei prompt: V2 immutato, V3 con le tre modifiche del giro 22/07.

    V2 è il prompt di produzione: il suo hash è fissato qui perché la baseline
    §8.9 (syllabus 8) è confrontabile solo a parità di prompt — se V2 cambia,
    questo test deve fallire e forzare una decisione esplicita.
    """

    def test_v2_hash_is_unchanged(self):
        # Genealogia: la baseline §8.9 (20/07) girò su 31f3335733e2; il 21/07
        # il commit 5758642 ha aggiunto a V2 la derivazione del "quarter" degli
        # eventi dalla sezione della storia cronometrica (campo NON coperto
        # dalla truth gold), portando l'hash a a0f50fbe5244. Se questo test
        # fallisce, V2 è cambiato di nuovo: aggiornare l'hash è una decisione
        # esplicita, perché rompe la confrontabilità dei run bench.
        import hashlib
        from matches.services.vision_providers import OCR_SYSTEM_PROMPT_V2
        self.assertEqual(
            hashlib.sha256(OCR_SYSTEM_PROMPT_V2.encode("utf-8")).hexdigest()[:12],
            "a0f50fbe5244",
        )

    def test_registry_exposes_v2_and_v3(self):
        from matches.services.vision_providers import (
            OCR_SYSTEM_PROMPT_V2, OCR_SYSTEM_PROMPT_V3, OCR_SYSTEM_PROMPTS,
        )
        self.assertEqual(
            OCR_SYSTEM_PROMPTS,
            {"v2": OCR_SYSTEM_PROMPT_V2, "v3": OCR_SYSTEM_PROMPT_V3},
        )

    def test_v3_contains_the_three_experimental_changes(self):
        from matches.services.vision_providers import OCR_SYSTEM_PROMPT_V3
        # (a) anti-riconciliazione sulla griglia parziali
        self.assertIn("NON aggiustare niente", OCR_SYSTEM_PROMPT_V3)
        self.assertIn("trascrizione\n             INDIPENDENTE", OCR_SYSTEM_PROMPT_V3)
        # (b) trascrizione letterale dei nomi
        self.assertIn("FRUSINO", OCR_SYSTEM_PROMPT_V3)
        self.assertIn("NON normalizzare MAI", OCR_SYSTEM_PROMPT_V3)
        # (c) data cifra per cifra + campi additivi dello schema
        self.assertIn("cifra per cifra", OCR_SYSTEM_PROMPT_V3)
        self.assertIn('"date_digits"', OCR_SYSTEM_PROMPT_V3)
        self.assertIn('"date": <0.0-1.0>', OCR_SYSTEM_PROMPT_V3)


class OcrZonePromptTest(TestCase):
    """Guardrail sul prompt del secondo passaggio (zone) e sui registri dei prompt."""

    def test_second_pass_registry_and_all_prompts(self):
        from matches.services.vision_providers import (
            OCR_SYSTEM_PROMPT_V2, OCR_SYSTEM_PROMPT_V3, OCR_SYSTEM_PROMPT_ZONE,
            OCR_SYSTEM_PROMPTS, OCR_SECOND_PASS_PROMPTS, OCR_ALL_PROMPTS,
        )
        # La registry di produzione resta v2/v3: zone è tenuta separata.
        self.assertEqual(
            OCR_SYSTEM_PROMPTS, {"v2": OCR_SYSTEM_PROMPT_V2, "v3": OCR_SYSTEM_PROMPT_V3}
        )
        self.assertEqual(OCR_SECOND_PASS_PROMPTS, {"zone": OCR_SYSTEM_PROMPT_ZONE})
        self.assertEqual(
            OCR_ALL_PROMPTS,
            {"v2": OCR_SYSTEM_PROMPT_V2, "v3": OCR_SYSTEM_PROMPT_V3,
             "zone": OCR_SYSTEM_PROMPT_ZONE},
        )

    def test_zone_prompt_inherits_v3_rules_and_is_minimal(self):
        from matches.services.vision_providers import OCR_SYSTEM_PROMPT_ZONE
        # eredita anti-riconciliazione (parziali = letture, discordanza non aggiustata)
        self.assertIn("NON aggiustare niente", OCR_SYSTEM_PROMPT_ZONE)
        self.assertIn("trascrizione INDIPENDENTE", OCR_SYSTEM_PROMPT_ZONE)
        # eredita la data cifra per cifra
        self.assertIn("cifra per cifra", OCR_SYSTEM_PROMPT_ZONE)
        self.assertIn('"date_digits"', OCR_SYSTEM_PROMPT_ZONE)
        # secondo atto di lettura, indipendente
        self.assertIn("SECONDO atto", OCR_SYSTEM_PROMPT_ZONE)
        # output minimale: niente roster/eventi/ufficiali
        self.assertNotIn("players", OCR_SYSTEM_PROMPT_ZONE)
        self.assertNotIn("officials", OCR_SYSTEM_PROMPT_ZONE)
        self.assertNotIn("events", OCR_SYSTEM_PROMPT_ZONE)

    def test_extract_data_resolves_zone_prompt(self):
        """extract_data accetta prompt_version='zone' (via OCR_ALL_PROMPTS)."""
        from matches.services.vision_providers import (
            GeminiVisionProvider, OCR_ALL_PROMPTS,
        )
        # Non facciamo la chiamata reale: verifichiamo solo che la risoluzione del
        # prompt non sollevi ValueError per 'zone' e la sollevi per un nome ignoto.
        self.assertIn("zone", OCR_ALL_PROMPTS)
        self.assertNotIn("zone", __import__(
            "matches.services.vision_providers", fromlist=["OCR_SYSTEM_PROMPTS"]
        ).OCR_SYSTEM_PROMPTS)


def zone_extraction(final_score, quarters, date, warnings=None, date_digits=None):
    """Estrazione 'solo zona' del secondo passaggio (schema minimale)."""
    return {
        "metadata": {
            "confidence": 0.95,
            "confidence_fields": {"final_score": 1.0, "quarters": 0.9, "date": 1.0},
            "extraction_warnings": warnings or [],
        },
        "match_info": {"date": date, "date_digits": date_digits},
        "scores": {"final_score": final_score, "quarters": quarters},
    }


class OcrBenchSecondPassTest(TestCase):
    """--second-pass: doppia estrazione per zona, confronto col primo passaggio riusato."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.cases_dir = os.path.join(self.tmp, "cases")
        self.first_dir = os.path.join(self.tmp, "first")
        self.out_dir = os.path.join(self.tmp, "out")
        self.media_root = os.path.join(self.tmp, "media")
        os.makedirs(self.cases_dir)
        override = override_settings(MEDIA_ROOT=self.media_root)
        override.enable()
        self.addCleanup(override.disable)
        self.report = MatchReport.objects.create(
            file=SimpleUploadedFile("referto_gold.jpg", b"gold image", content_type="image/jpeg"),
            status=MatchReport.Status.NEEDS_REVIEW,
        )
        self.case_id = "2026-01-01_test-home_vs_test-away"
        case = {
            "case_id": self.case_id,
            "verified_by": "Test Umano",
            "match": {
                "date": "2026-01-01",
                "home_team": {"name_on_paper": "CASA"},
                "away_team": {"name_on_paper": "OSPITI"},
            },
            "truth": {
                "scores": {
                    "final_score": "4-19",
                    "quarters": {"1": [1, 3], "2": [0, 5], "3": [3, 6], "4": [0, 5]},
                }
            },
            "not_verified": [],
            "extractions": [{"db_report_pk": self.report.pk}],
        }
        with open(os.path.join(self.cases_dir, f"{self.case_id}.json"), "w") as f:
            json.dump(case, f)

    def _call_bench(self, factory, *args):
        with patch("matches.management.commands.ocr_bench.GeminiVisionProvider") as mock_class:
            mock_provider = MagicMock()
            mock_class.return_value = mock_provider

            def _fake_extract(report, model=None, preprocess=True,
                              sent_image_callback=None, prompt_version=None):
                return factory(model, prompt_version), "raw"

            mock_provider.extract_data.side_effect = _fake_extract
            out = StringIO()
            call_command(
                "ocr_bench", "--models", "gemini-2.5-pro",
                "--cases-dir", self.cases_dir, *args, stdout=out,
            )
            return out.getvalue()

    def _gen_first_pass(self, first_data, repeat=3):
        """Genera la proposta del primo passaggio in first_dir (schema --repeat)."""
        self._call_bench(
            lambda model, pv: first_data,
            "--gold-case", self.case_id, "--repeat", str(repeat),
            "--out-dir", self.first_dir,
        )

    def _run_second_pass(self, zone_data, repeat=3):
        return self._call_bench(
            lambda model, pv: zone_data,
            "--gold-case", self.case_id, "--repeat", str(repeat),
            "--second-pass", "--first-pass-dir", self.first_dir,
            "--out-dir", self.out_dir,
        )

    def _second_pass_proposal(self):
        files = [f for f in os.listdir(self.out_dir) if "_secondpass" in f]
        self.assertEqual(len(files), 1)
        with open(os.path.join(self.out_dir, files[0])) as f:
            return json.load(f)

    def test_second_pass_flags_divergence_on_final_score(self):
        """Primo legge 5-19 (sbagliato), secondo 4-19 (giusto): divergenza -> review."""
        first = zone_extraction(
            "5-19", {"1": [1, 3], "2": [0, 5], "3": [3, 6], "4": [0, 5]}, "2026-01-01"
        )
        zone = zone_extraction(
            "4-19", {"1": [1, 3], "2": [0, 5], "3": [3, 6], "4": [0, 5]}, "2026-01-01"
        )
        self._gen_first_pass(first, repeat=3)
        output = self._run_second_pass(zone, repeat=3)
        self.assertIn("DIVERGE", output)
        self.assertIn("NEEDS_REVIEW", output)
        proposal = self._second_pass_proposal()
        self.assertEqual(proposal["mode"], "second_pass_divergence")
        self.assertEqual(proposal["summary"]["repeats_compared"], 3)
        self.assertEqual(proposal["summary"]["repeats_diverging"], 3)
        self.assertEqual(proposal["summary"]["by_zone"]["final_score"], 3)
        self.assertEqual(proposal["summary"]["by_zone"]["quarters"], 0)
        self.assertTrue(proposal["summary"]["needs_review_any"])
        self.assertEqual(
            proposal["repeats"][0]["divergence"]["diverging_zones"], ["final_score"]
        )

    def test_second_pass_no_divergence_when_reads_agree(self):
        agree = zone_extraction(
            "4-19", {"1": [1, 3], "2": [0, 5], "3": [3, 6], "4": [0, 5]}, "2026-01-01"
        )
        self._gen_first_pass(agree, repeat=2)
        output = self._run_second_pass(agree, repeat=2)
        self.assertIn("concorde", output)
        proposal = self._second_pass_proposal()
        self.assertEqual(proposal["summary"]["repeats_diverging"], 0)
        self.assertFalse(proposal["summary"]["needs_review_any"])

    def test_second_pass_persists_zone_extraction_warnings(self):
        first = zone_extraction("4-19", {"1": [1, 3]}, "2026-01-01")
        zone = zone_extraction(
            "4-19", {"1": [1, 3]}, "2026-01-01",
            warnings=["somma parziali != finale casa (segnalata)"],
        )
        self._gen_first_pass(first, repeat=2)
        self._run_second_pass(zone, repeat=2)
        proposal = self._second_pass_proposal()
        self.assertEqual(
            proposal["repeats"][0]["second"]["extraction_warnings"],
            ["somma parziali != finale casa (segnalata)"],
        )

    def test_second_pass_requires_first_pass_dir(self):
        with self.assertRaises(CommandError):
            self._call_bench(
                lambda model, pv: zone_extraction("4-19", {}, "2026-01-01"),
                "--gold-case", self.case_id, "--second-pass", "--out-dir", self.out_dir,
            )

    def test_first_pass_dir_requires_second_pass(self):
        with self.assertRaises(CommandError):
            self._call_bench(
                lambda model, pv: zone_extraction("4-19", {}, "2026-01-01"),
                "--gold-case", self.case_id,
                "--first-pass-dir", self.first_dir, "--out-dir", self.out_dir,
            )

    def test_second_pass_requires_gold_mode(self):
        fd, loose = tempfile.mkstemp(suffix=".jpg", dir=self.tmp)
        with os.fdopen(fd, "wb") as f:
            f.write(b"img")
        os.makedirs(self.first_dir, exist_ok=True)
        with self.assertRaises(CommandError):
            self._call_bench(
                lambda model, pv: zone_extraction("4-19", {}, "2026-01-01"),
                "--image", loose, "--second-pass", "--first-pass-dir", self.first_dir,
            )
