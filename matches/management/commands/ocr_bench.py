"""
Bench read-only per confrontare modelli OCR sulla stessa immagine di referto.

Per ogni modello richiesto esegue una estrazione reale (chiamata OpenAI,
costo reale) e stampa confidence auto-dichiarata, latenza e token usage.
Con --report-id confronta l'estrazione grezza con i dati validati
(normalized_data post-review) e stampa un accuracy exact-match per campo.

Nessuna scrittura sul DB: niente salvataggi di MatchReport/OCRRawResponse,
niente transizioni di stato.
"""
import time
from types import SimpleNamespace

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from matches.models import MatchReport
from matches.services.vision_providers import GPT4oVisionProvider

# Campi top-level confrontati per l'accuracy exact-match
ACCURACY_FIELDS = [
    "home_team",
    "away_team",
    "final_score",
    "quarters_count",
    "home_roster_count",
    "away_roster_count",
    "events_count",
]


def extract_comparable_fields(data):
    """Estrae i campi top-level confrontabili da un dict in schema OCR v2."""
    info = data.get("match_info") or {}
    scores = data.get("scores") or {}
    teams = data.get("teams") or {}
    return {
        "home_team": info.get("home_team"),
        "away_team": info.get("away_team"),
        "final_score": scores.get("final_score"),
        "quarters_count": len(scores.get("quarters") or {}),
        "home_roster_count": len((teams.get("home") or {}).get("players") or []),
        "away_roster_count": len((teams.get("away") or {}).get("players") or []),
        "events_count": len(data.get("events") or []),
    }


class Command(BaseCommand):
    help = (
        "Confronta modelli OCR sulla stessa immagine (read-only, chiamate reali a OpenAI). "
        "Uso: ocr_bench --image <path> [--models gpt-4o,gpt-4o-mini] [--report-id <id>]"
    )

    def add_arguments(self, parser):
        parser.add_argument("--image", required=True, help="Path dell'immagine del referto")
        parser.add_argument(
            "--models",
            default=None,
            help="Lista di modelli separati da virgola (default: settings.OCR_MODEL)",
        )
        parser.add_argument(
            "--report-id",
            type=int,
            default=None,
            help="Se il report ha normalized_data validati, calcola accuracy exact-match per campo",
        )

    def handle(self, *args, **options):
        import os

        image_path = options["image"]
        if not os.path.isfile(image_path):
            raise CommandError(f"Immagine non trovata: {image_path}")

        if options["models"]:
            models = [m.strip() for m in options["models"].split(",") if m.strip()]
        else:
            models = [getattr(settings, "OCR_MODEL", "gpt-4o")]
        if not models:
            raise CommandError("Nessun modello specificato.")

        validated_fields = None
        if options["report_id"] is not None:
            try:
                report = MatchReport.objects.get(pk=options["report_id"])
            except MatchReport.DoesNotExist:
                raise CommandError(f"MatchReport {options['report_id']} non trovato.")
            if report.normalized_data:
                validated_fields = extract_comparable_fields(report.normalized_data)
                self.stdout.write(
                    f"Baseline validata: report {report.pk} (normalized_data post-review)"
                )
            else:
                self.stdout.write(self.style.WARNING(
                    f"Report {report.pk} senza normalized_data: accuracy non calcolabile."
                ))

        provider = GPT4oVisionProvider()
        # Stub minimale: extract_data usa solo .id (logging) e .file.path
        bench_report = SimpleNamespace(
            id=f"bench:{os.path.basename(image_path)}",
            file=SimpleNamespace(path=image_path),
        )

        self.stdout.write(f"\nImmagine: {image_path}")
        self.stdout.write(f"Modelli: {', '.join(models)}\n")
        header = f"{'modello':<20} {'confidence':>10} {'latenza':>9} {'tok_in':>8} {'tok_out':>8}"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))

        results = {}
        for model in models:
            start = time.monotonic()
            try:
                data, _raw = provider.extract_data(bench_report, model=model)
            except Exception as e:
                elapsed = time.monotonic() - start
                self.stdout.write(self.style.ERROR(
                    f"{model:<20} {'ERRORE':>10} {elapsed:>8.1f}s  {e}"
                ))
                continue
            elapsed = time.monotonic() - start
            meta = data.get("metadata") or {}
            confidence = meta.get("confidence")
            usage = meta.get("token_usage") or {}
            conf_str = f"{confidence:.2f}" if isinstance(confidence, (int, float)) else "N/A"
            tok_in = usage.get("prompt_tokens")
            tok_out = usage.get("completion_tokens")
            self.stdout.write(
                f"{model:<20} {conf_str:>10} {elapsed:>8.1f}s "
                f"{tok_in if tok_in is not None else 'N/A':>8} "
                f"{tok_out if tok_out is not None else 'N/A':>8}"
            )
            results[model] = data

        if validated_fields is not None and results:
            self.stdout.write("\nAccuracy exact-match vs dati validati:")
            for model, data in results.items():
                extracted = extract_comparable_fields(data)
                hits = [f for f in ACCURACY_FIELDS if extracted[f] == validated_fields[f]]
                misses = [f for f in ACCURACY_FIELDS if f not in hits]
                self.stdout.write(
                    f"  {model:<20} {len(hits)}/{len(ACCURACY_FIELDS)}"
                    + (f"  (mismatch: {', '.join(misses)})" if misses else "")
                )
                for f in misses:
                    self.stdout.write(
                        f"    - {f}: estratto={extracted[f]!r} vs validato={validated_fields[f]!r}"
                    )
