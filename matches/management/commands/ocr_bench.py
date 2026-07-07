"""
Bench read-only per confrontare modelli OCR sulla stessa immagine di referto.

Per ogni modello richiesto esegue una estrazione reale (chiamata OpenAI,
costo reale) e stampa confidence auto-dichiarata, latenza e token usage.
Con --report-id confronta l'estrazione grezza con i dati validati
(normalized_data post-review) e stampa un accuracy exact-match per campo.
Con --show stampa un blocco leggibile per modello con i campi chiave estratti
(squadre, punteggio, quarti, roster, eventi) per il confronto a occhio col
referto fisico. Con --save-dir <path> salva il JSON completo estratto da
ciascun modello in <path>/ocr_bench_<model>_<timestamp>.json.
Con --dump-sent-image <dir> salva su disco l'immagine esattamente inviata al
modello (output del preprocessing, o i byte grezzi con --no-preprocess) come
<dir>/ocr_bench_sent_<model>_<timestamp>.<ext>; il dump avviene prima della
chiamata API, quindi anche se la chiamata poi fallisce.
Con --no-preprocess bypassa ImagePreprocessor e invia l'immagine grezza
(niente auto-rotate a portrait né downscale).

Nessuna scrittura sul DB: niente salvataggi di MatchReport/OCRRawResponse,
niente transizioni di stato.
"""
import json
import re
import shutil
import time
from types import SimpleNamespace

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from matches.models import MatchReport
from matches.services.vision_providers import GPT4oVisionProvider, GeminiVisionProvider

# Mappa provider bench: nome CLI -> (setting del modello di default, fallback).
# NB: la CLASSE del provider viene risolta a runtime dentro handle() leggendo i
# simboli di questo modulo, così i test possono patchare GPT4oVisionProvider /
# GeminiVisionProvider senza che un riferimento catturato all'import li scavalchi.
PROVIDER_MODEL_SETTINGS = {
    "openai": ("OCR_MODEL", "gpt-4o"),
    "gemini": ("GEMINI_MODEL", "gemini-2.5-flash"),
}

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


ASSENTE = "— assente"


def safe_model_slug(model):
    """Rende il nome del modello sicuro per l'uso in un nome di file."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model)


def build_show_block(model, data):
    """Righe leggibili con i campi chiave estratti da un modello (per --show)."""
    info = data.get("match_info") or {}
    scores = data.get("scores") or {}
    teams = data.get("teams") or {}
    events = data.get("events") or []

    lines = [f"=== {model} ==="]
    lines.append(f"  home_team:   {info.get('home_team') or ASSENTE}")
    lines.append(f"  away_team:   {info.get('away_team') or ASSENTE}")
    lines.append(f"  final_score: {scores.get('final_score') or ASSENTE}")

    quarters = scores.get("quarters") or {}
    if quarters:
        parts = " | ".join(f"{q}: {v}" for q, v in quarters.items())
        lines.append(f"  quarti ({len(quarters)}): {parts}")
    else:
        lines.append(f"  quarti: {ASSENTE}")

    for side, label in (("home", "roster casa"), ("away", "roster ospiti")):
        players = (teams.get(side) or {}).get("players") or []
        if players:
            elenco = ", ".join(
                f"{p.get('number') if p.get('number') is not None else '?'} "
                f"{p.get('name') or ASSENTE}"
                for p in players
            )
            lines.append(f"  {label} ({len(players)}): {elenco}")
        else:
            lines.append(f"  {label}: {ASSENTE}")

    if events:
        lines.append(f"  eventi ({len(events)}):")
        for ev in events:
            desc = ev.get("type") or ASSENTE
            if ev.get("player_name"):
                desc += f" — {ev['player_name']}"
            extra = [str(x) for x in (ev.get("team"),) if x]
            if ev.get("quarter") is not None:
                extra.append(f"Q{ev['quarter']}")
            if extra:
                desc += f" ({', '.join(extra)})"
            lines.append(f"    - {desc}")
    else:
        lines.append(f"  eventi: {ASSENTE}")
    return lines


class Command(BaseCommand):
    help = (
        "Confronta modelli OCR sulla stessa immagine (read-only, chiamate reali all'LLM). "
        "Uso: ocr_bench --image <path> [--provider openai|gemini] "
        "[--models gpt-4o,gpt-4o-mini] [--report-id <id>] [--show] [--save-dir <path>]"
    )

    def add_arguments(self, parser):
        parser.add_argument("--image", required=True, help="Path dell'immagine del referto")
        parser.add_argument(
            "--provider",
            choices=sorted(PROVIDER_MODEL_SETTINGS.keys()),
            default="openai",
            help="Provider da istanziare per questo run (default: openai). "
                 "Lancia lo stesso referto con --provider gemini per confrontarli.",
        )
        parser.add_argument(
            "--models",
            default=None,
            help="Lista di modelli separati da virgola "
                 "(default: modello del provider da settings, es. OCR_MODEL / GEMINI_MODEL)",
        )
        parser.add_argument(
            "--report-id",
            type=int,
            default=None,
            help="Se il report ha normalized_data validati, calcola accuracy exact-match per campo",
        )
        parser.add_argument(
            "--show",
            action="store_true",
            help="Stampa un blocco leggibile per modello con i campi chiave estratti",
        )
        parser.add_argument(
            "--save-dir",
            default=None,
            help="Salva il JSON completo estratto da ciascun modello in <path>/ocr_bench_<model>_<timestamp>.json",
        )
        parser.add_argument(
            "--dump-sent-image",
            default=None,
            metavar="DIR",
            help=(
                "Salva in DIR l'immagine esattamente inviata al modello come "
                "ocr_bench_sent_<model>_<timestamp>.<ext> (crea DIR se manca)"
            ),
        )
        parser.add_argument(
            "--no-preprocess",
            action="store_true",
            help="Bypassa ImagePreprocessor e invia l'immagine grezza (no auto-rotate, no downscale)",
        )

    def handle(self, *args, **options):
        import os

        image_path = options["image"]
        if not os.path.isfile(image_path):
            raise CommandError(f"Immagine non trovata: {image_path}")

        provider_name = options["provider"]
        model_setting, model_fallback = PROVIDER_MODEL_SETTINGS[provider_name]
        # Risoluzione a runtime: rispetta gli eventuali patch dei test.
        provider_cls = {
            "openai": GPT4oVisionProvider,
            "gemini": GeminiVisionProvider,
        }[provider_name]

        if options["models"]:
            models = [m.strip() for m in options["models"].split(",") if m.strip()]
        else:
            models = [getattr(settings, model_setting, model_fallback)]
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

        provider = provider_cls()
        # Stub minimale: extract_data usa solo .id (logging) e .file.path
        bench_report = SimpleNamespace(
            id=f"bench:{os.path.basename(image_path)}",
            file=SimpleNamespace(path=image_path),
        )

        preprocess = not options["no_preprocess"]
        dump_dir = options["dump_sent_image"]
        if dump_dir:
            os.makedirs(dump_dir, exist_ok=True)

        self.stdout.write(f"\nImmagine: {image_path}")
        self.stdout.write(f"Provider: {provider_name}")
        self.stdout.write(f"Modelli: {', '.join(models)}")
        if not preprocess:
            self.stdout.write("Preprocessing: BYPASSATO (--no-preprocess)")
        self.stdout.write("")
        header = f"{'modello':<20} {'confidence':>10} {'latenza':>9} {'tok_in':>8} {'tok_out':>8}"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))

        results = {}
        dumped_paths = []
        for model in models:
            # Solo kwargs non-default: il contratto della chiamata senza nuovi
            # flag resta identico a prima.
            extract_kwargs = {"model": model}
            if not preprocess:
                extract_kwargs["preprocess"] = False
            if dump_dir:
                ts = timezone.localtime().strftime("%Y%m%d_%H%M%S")

                def dump_sent(sent_path, _model=model, _ts=ts):
                    ext = os.path.splitext(sent_path)[1] or ".jpg"
                    dest = os.path.join(
                        dump_dir, f"ocr_bench_sent_{safe_model_slug(_model)}_{_ts}{ext}"
                    )
                    shutil.copyfile(sent_path, dest)
                    dumped_paths.append(dest)

                extract_kwargs["sent_image_callback"] = dump_sent

            start = time.monotonic()
            try:
                data, _raw = provider.extract_data(bench_report, **extract_kwargs)
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

        if dumped_paths:
            self.stdout.write("")
            for path in dumped_paths:
                self.stdout.write(f"Immagine inviata salvata: {path}")

        if options["show"] and results:
            for model, data in results.items():
                self.stdout.write("")
                for line in build_show_block(model, data):
                    self.stdout.write(line)

        if options["save_dir"] and results:
            save_dir = options["save_dir"]
            os.makedirs(save_dir, exist_ok=True)
            ts = timezone.localtime().strftime("%Y%m%d_%H%M%S")
            self.stdout.write("")
            for model, data in results.items():
                path = os.path.join(
                    save_dir, f"ocr_bench_{safe_model_slug(model)}_{ts}.json"
                )
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                self.stdout.write(f"Salvato: {path}")

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
