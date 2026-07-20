"""
Bench read-only per confrontare modelli OCR sulla stessa immagine di referto.

Per ogni modello richiesto esegue una estrazione reale (chiamata all'LLM,
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

Modalità gold standard (Macro 8):
  --gold-case <case_id>   un caso di docs/ocr_gold_standard/cases/
  --gold-all              tutti i casi (glob su cases/*.json)
Confronta l'estrazione con la `truth` verificata da umano del caso, campo per
campo e mai aggregato: final_score spaccato home/away, gli 8 valori dei quarti
separati, nomi squadre contro `name_on_paper` (non il nome a DB), esito
ternario correct/wrong/null (il null è conteggiato a parte, non come errore),
check esplicito di inversione casa/trasferta, confidence auto-dichiarata
accostata a ogni verdetto. Si confrontano SOLO i campi presenti in `truth`:
ciò che sta in `not_verified` è ignorato per costruzione.
L'immagine si risolve dai `db_report_pk` del caso (file del MatchReport), o da
--image esplicito (solo con --gold-case) per i casi senza report a DB.
Ogni estrazione produce un file di PROPOSTA in --out-dir (default
<BASE_DIR>/ocr_bench_out/gold/, gitignorata), nello schema delle voci
extractions[] dei casi gold. La proposta NON viene mai scritta nel caso:
il riversamento in extractions[] resta un atto umano dopo review (decisione
D1: un bug del bench non deve poter inquinare la verità).

Nessuna scrittura sul DB: niente salvataggi di MatchReport,
niente transizioni di stato.
"""
import glob
import hashlib
import json
import os
import re
import shutil
import time
from types import SimpleNamespace

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from matches.models import MatchReport
from matches.services.vision_providers import GeminiVisionProvider, OCR_SYSTEM_PROMPT_V2

# Mappa provider bench: nome CLI -> (setting del modello di default, fallback).
# NB: la CLASSE del provider viene risolta a runtime dentro handle() leggendo i
# simboli di questo modulo, così i test possono patchare GeminiVisionProvider
# senza che un riferimento catturato all'import lo scavalchi. Il seam resta
# estendibile: aggiungere un provider = una entry qui + una nel map in handle().
PROVIDER_MODEL_SETTINGS = {
    "gemini": ("GEMINI_MODEL", "gemini-2.5-pro"),
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

# --- Modalità gold standard -------------------------------------------------

GOLD_CASES_DIR_DEFAULT = os.path.join("docs", "ocr_gold_standard", "cases")
GOLD_OUT_DIR_DEFAULT = os.path.join("ocr_bench_out", "gold")

# Versione del prompt registrata in ogni run: nome del simbolo + hash del testo.
# L'hash cambia se il prompt cambia, quindi due run sono confrontabili solo a
# parità di questa stringa. Read-only sulla pipeline: il prompt non si tocca.
PROMPT_VERSION = "OCR_SYSTEM_PROMPT_V2@sha256:" + hashlib.sha256(
    OCR_SYSTEM_PROMPT_V2.encode("utf-8")
).hexdigest()[:12]


def normalize_team_name(name):
    """Normalizza un nome squadra per il confronto col foglio (maiuscole, solo alfanumerici).

    'S.S. LAZIO NUOTO' e 'SS LAZIO NUOTO' devono risultare uguali: la
    punteggiatura non è un errore di lettura.
    """
    if not isinstance(name, str):
        return None
    return re.sub(r"[^A-Z0-9]", "", name.upper()) or None


def parse_final_score(value):
    """'X-Y' -> (X, Y) come interi; None se null o non parsabile."""
    if not isinstance(value, str):
        return None
    m = re.match(r"^\s*(\d+)\s*[-–]\s*(\d+)\s*$", value)
    return (int(m.group(1)), int(m.group(2))) if m else None


def quarter_value(quarters, key, side):
    """Valore di un lato (0=home, 1=away) di un quarto; None se assente/null."""
    if not isinstance(quarters, dict):
        return None
    q = quarters.get(key) if key in quarters else quarters.get(str(key))
    if not isinstance(q, (list, tuple)) or len(q) != 2:
        return None
    v = q[side]
    return v if isinstance(v, int) else None


def confidence_key_for(field):
    """Mappa un campo del bench sulla chiave di metadata.confidence_fields."""
    if field.startswith("final_score"):
        return "final_score"
    if field.startswith("quarter_"):
        return "quarters"
    if field == "home_team_name":
        return "home_team"
    if field == "away_team_name":
        return "away_team"
    if field == "date":
        return None
    return None


def compare_extraction_to_truth(case, data):
    """Confronta un'estrazione (schema OCR v2) con la truth di un caso gold.

    Ritorna (fields, inversion):
      fields: dict ordinato campo -> {truth, extracted, verdict, confidence}
              con verdict in {correct, wrong, null}. Solo campi presenti in
              truth (più i name_on_paper e la data del blocco match, anch'essi
              verificati da umano). null = il provider ha dichiarato di non
              saper leggere: conteggiato a parte, mai come errore.
      inversion: check esplicito casa/trasferta — valori giusti attribuiti
              alla squadra sbagliata (classe di errore del match 2), invisibile
              al confronto campo-per-campo.
    """
    truth_scores = (case.get("truth") or {}).get("scores") or {}
    case_match = case.get("match") or {}
    ext_scores = data.get("scores") or {}
    ext_info = data.get("match_info") or {}
    conf_fields = (data.get("metadata") or {}).get("confidence_fields") or {}

    fields = {}

    def add(field, truth_v, ext_v, verdict=None):
        if verdict is None:
            if ext_v is None:
                verdict = "null"
            elif ext_v == truth_v:
                verdict = "correct"
            else:
                verdict = "wrong"
        conf_key = confidence_key_for(field)
        fields[field] = {
            "truth": truth_v,
            "extracted": ext_v,
            "verdict": verdict,
            "confidence": conf_fields.get(conf_key) if conf_key else None,
        }

    # final_score spaccato in home e away separati
    truth_final = parse_final_score(truth_scores.get("final_score"))
    raw_final = ext_scores.get("final_score")
    ext_final = parse_final_score(raw_final)
    if truth_final:
        if raw_final is not None and ext_final is None:
            # Valorizzato ma non parsabile: non è un null dichiarato, è un errore.
            add("final_score_home", truth_final[0], raw_final, verdict="wrong")
            add("final_score_away", truth_final[1], raw_final, verdict="wrong")
        else:
            add("final_score_home", truth_final[0], ext_final[0] if ext_final else None)
            add("final_score_away", truth_final[1], ext_final[1] if ext_final else None)

    # gli 8 valori dei quarti, separatamente
    truth_quarters = truth_scores.get("quarters") or {}
    ext_quarters = ext_scores.get("quarters") or {}
    for k in sorted(truth_quarters, key=str):
        for side, label in ((0, "home"), (1, "away")):
            tv = quarter_value(truth_quarters, k, side)
            if tv is None:
                continue  # quarto non in truth: fuori dal confronto
            add(f"quarter_{k}_{label}", tv, quarter_value(ext_quarters, k, side))

    # nomi squadre contro name_on_paper (NON il nome a DB: la divergenza
    # foglio<->DB è un problema della discovery, non dell'OCR)
    paper = {}
    for side_key, field in (("home_team", "home_team_name"), ("away_team", "away_team_name")):
        name_on_paper = (case_match.get(side_key) or {}).get("name_on_paper")
        paper[side_key] = name_on_paper
        if name_on_paper:
            ext_name = ext_info.get(side_key)
            if ext_name is None:
                add(field, name_on_paper, None)
            else:
                equal = normalize_team_name(ext_name) == normalize_team_name(name_on_paper)
                add(field, name_on_paper, ext_name, verdict="correct" if equal else "wrong")

    # data come scritta sul referto (blocco match, verificata da umano)
    truth_date = case_match.get("date")
    if truth_date:
        add("date", truth_date, ext_info.get("date"))

    # --- check esplicito di inversione casa/trasferta ---
    inversion = {"final_score": None, "quarters": {}, "team_names": None}
    if truth_final and ext_final and truth_final[0] != truth_final[1]:
        inversion["final_score"] = (
            ext_final == (truth_final[1], truth_final[0]) and ext_final != truth_final
        )
    for k in sorted(truth_quarters, key=str):
        th = quarter_value(truth_quarters, k, 0)
        ta = quarter_value(truth_quarters, k, 1)
        eh = quarter_value(ext_quarters, k, 0)
        ea = quarter_value(ext_quarters, k, 1)
        if None in (th, ta, eh, ea) or th == ta:
            inversion["quarters"][str(k)] = None  # non computabile (null o truth simmetrica)
        else:
            inversion["quarters"][str(k)] = (eh, ea) == (ta, th)
    norm_paper_home = normalize_team_name(paper.get("home_team"))
    norm_paper_away = normalize_team_name(paper.get("away_team"))
    norm_ext_home = normalize_team_name(ext_info.get("home_team"))
    norm_ext_away = normalize_team_name(ext_info.get("away_team"))
    if all((norm_paper_home, norm_paper_away, norm_ext_home, norm_ext_away)) \
            and norm_paper_home != norm_paper_away:
        inversion["team_names"] = (
            norm_ext_home == norm_paper_away and norm_ext_away == norm_paper_home
        )
    inversion["any"] = any(
        v is True
        for v in [inversion["final_score"], inversion["team_names"], *inversion["quarters"].values()]
    )
    return fields, inversion


def build_gold_proposal(case, data, provider_label, model, resolved_pk, image_path,
                        image_resolved_from, preprocess, fields, inversion, run_ts):
    """Costruisce la voce di proposta nello schema di extractions[] dei casi gold.

    È una PROPOSTA: va salvata nella directory di output, mai dentro il caso.
    Il riversamento in extractions[] è un atto umano dopo review (decisione D1).
    """
    meta = data.get("metadata") or {}
    ext_info = data.get("match_info") or {}
    ext_scores = data.get("scores") or {}
    teams = data.get("teams") or {}
    confidence = {"overall": meta.get("confidence")}
    confidence.update(meta.get("confidence_fields") or {})
    verdict = {f: v["verdict"] for f, v in fields.items()}
    # Come nello schema esistente: ciò che non è in truth resta unverified.
    verdict.setdefault("roster", "unverified")
    verdict.setdefault("events", "unverified")
    return {
        "case_id": case.get("case_id"),
        "provider": meta.get("provider") or provider_label,
        "model": model,
        "db_report_pk": resolved_pk,
        "extracted_at": run_ts.date().isoformat(),
        "extracted": {
            "match_info": {k: ext_info.get(k) for k in ("home_team", "away_team", "date")},
            "scores": {
                "final_score": ext_scores.get("final_score"),
                "quarters": ext_scores.get("quarters"),
            },
            "counts": {
                "events": len(data.get("events") or []),
                "home_roster": len((teams.get("home") or {}).get("players") or []),
                "away_roster": len((teams.get("away") or {}).get("players") or []),
            },
        },
        "self_reported_confidence": confidence,
        "verdict": verdict,
        "inversion_check": inversion,
        "comparison": fields,
        "bench_run": {
            "provider_cli": provider_label,
            "model": model,
            "prompt_version": PROMPT_VERSION,
            "preprocessing": preprocess,
            "timestamp": run_ts.isoformat(),
            "image": image_path,
            "image_resolved_from": image_resolved_from,
        },
        "notes": [
            "Proposta generata da ocr_bench --gold: riversare in extractions[] "
            "solo dopo review umana (decisione D1)."
        ],
    }


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
        "Uso: ocr_bench --image <path> [--provider gemini] "
        "[--models gemini-2.5-pro,gemini-2.5-flash] [--report-id <id>] [--show] [--save-dir <path>] "
        "| ocr_bench --gold-case <case_id> [--image <path>] | ocr_bench --gold-all "
        "(confronto con la truth dei casi gold; proposte in --out-dir, mai nei casi)"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--image",
            default=None,
            help="Path dell'immagine del referto (obbligatorio senza --gold-case/--gold-all; "
                 "con --gold-case è l'override per i casi senza report a DB)",
        )
        parser.add_argument(
            "--gold-case",
            default=None,
            metavar="CASE_ID",
            help="Confronta l'estrazione con la truth del caso gold indicato "
                 "(nome file senza .json in docs/ocr_gold_standard/cases/)",
        )
        parser.add_argument(
            "--gold-all",
            action="store_true",
            help="Come --gold-case, per tutti i casi (glob su cases/*.json); "
                 "i casi senza immagine risolvibile vengono saltati con avviso",
        )
        parser.add_argument(
            "--cases-dir",
            default=None,
            help=f"Directory dei casi gold (default: <BASE_DIR>/{GOLD_CASES_DIR_DEFAULT})",
        )
        parser.add_argument(
            "--out-dir",
            default=None,
            help="Directory dove salvare le proposte di estrazione in modalità gold "
                 f"(default: <BASE_DIR>/{GOLD_OUT_DIR_DEFAULT}, gitignorata). "
                 "Le proposte non vengono MAI scritte nei file dei casi.",
        )
        parser.add_argument(
            "--provider",
            choices=sorted(PROVIDER_MODEL_SETTINGS.keys()),
            default="gemini",
            help="Provider da istanziare per questo run (default: gemini).",
        )
        parser.add_argument(
            "--models",
            default=None,
            help="Lista di modelli separati da virgola "
                 "(default: modello del provider da settings, es. GEMINI_MODEL)",
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
        image_opt = options["image"]
        gold_case_id = options["gold_case"]
        gold_all = options["gold_all"]
        gold_mode = bool(gold_case_id or gold_all)

        if gold_case_id and gold_all:
            raise CommandError("--gold-case e --gold-all sono alternativi.")
        if gold_all and image_opt:
            raise CommandError(
                "--image non è combinabile con --gold-all: usalo con --gold-case "
                "per i casi senza report a DB."
            )
        if not gold_mode and not image_opt:
            raise CommandError("Serve --image, oppure --gold-case/--gold-all.")
        if gold_mode and options["report_id"] is not None:
            raise CommandError(
                "--report-id non è combinabile con la modalità gold: "
                "la baseline dei casi gold è la loro truth."
            )
        if image_opt and not os.path.isfile(image_opt):
            raise CommandError(f"Immagine non trovata: {image_opt}")

        provider_name = options["provider"]
        model_setting, model_fallback = PROVIDER_MODEL_SETTINGS[provider_name]
        # Risoluzione a runtime: rispetta gli eventuali patch dei test.
        provider_cls = {
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
        provider_label = provider_name

        preprocess = not options["no_preprocess"]
        dump_dir = options["dump_sent_image"]
        if dump_dir:
            os.makedirs(dump_dir, exist_ok=True)

        if not gold_mode:
            results = self._run_models(
                provider, provider_name, models, image_opt, preprocess, dump_dir
            )
            self._print_show_and_save(results, options)
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
            return

        # --- modalità gold: confronto con la truth verificata da umano ---
        cases_dir = options["cases_dir"] or os.path.join(
            settings.BASE_DIR, GOLD_CASES_DIR_DEFAULT
        )
        if gold_case_id:
            case_paths = [os.path.join(cases_dir, f"{gold_case_id}.json")]
            if not os.path.isfile(case_paths[0]):
                available = sorted(
                    os.path.splitext(os.path.basename(p))[0]
                    for p in glob.glob(os.path.join(cases_dir, "*.json"))
                )
                raise CommandError(
                    f"Caso gold '{gold_case_id}' non trovato in {cases_dir}. "
                    f"Disponibili: {', '.join(available) or 'nessuno'}"
                )
        else:
            case_paths = sorted(glob.glob(os.path.join(cases_dir, "*.json")))
            if not case_paths:
                raise CommandError(f"Nessun caso gold in {cases_dir}.")

        out_dir = options["out_dir"] or os.path.join(settings.BASE_DIR, GOLD_OUT_DIR_DEFAULT)
        os.makedirs(out_dir, exist_ok=True)

        run_ts = timezone.localtime()
        self.stdout.write(f"Run gold: provider={provider_name} modelli={', '.join(models)}")
        self.stdout.write(f"  prompt: {PROMPT_VERSION}")
        self.stdout.write(f"  preprocessing: {'on' if preprocess else 'off'}")
        self.stdout.write(f"  timestamp: {run_ts.isoformat()}")
        self.stdout.write(f"  output proposte: {out_dir}")

        skipped = []
        for case_path in case_paths:
            case = self._load_gold_case(case_path, strict=bool(gold_case_id))
            if case is None:
                skipped.append((os.path.basename(case_path), "JSON non leggibile"))
                continue
            case_id = case.get("case_id") or os.path.splitext(os.path.basename(case_path))[0]

            if gold_case_id and image_opt:
                image_path, resolved_pk, resolved_from = image_opt, None, "--image"
            else:
                image_path, resolved_pk, err = self._resolve_case_image(case)
                resolved_from = f"db_report_pk={resolved_pk}" if resolved_pk else None
                if image_path is None:
                    if gold_case_id:
                        raise CommandError(
                            f"Caso '{case_id}': {err} Usa --image per fornire il file."
                        )
                    self.stdout.write(self.style.WARNING(f"\nCaso '{case_id}' SALTATO: {err}"))
                    skipped.append((case_id, err))
                    continue

            self.stdout.write(f"\n=== Caso gold: {case_id} ===")
            results = self._run_models(
                provider, provider_name, models, image_path, preprocess, dump_dir
            )
            self._print_show_and_save(results, options, case_id=case_id)

            for model, data in results.items():
                fields, inversion = compare_extraction_to_truth(case, data)
                self._print_gold_comparison(case_id, model, fields, inversion)
                proposal = build_gold_proposal(
                    case, data, provider_label, model, resolved_pk, image_path,
                    resolved_from, preprocess, fields, inversion, run_ts,
                )
                fname = (
                    f"{case_id}__{safe_model_slug(model)}_"
                    f"{run_ts.strftime('%Y%m%d_%H%M%S')}.json"
                )
                path = os.path.join(out_dir, fname)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(proposal, f, indent=2, ensure_ascii=False)
                self.stdout.write(
                    f"Proposta salvata: {path} "
                    "(riversamento in extractions[] manuale, dopo review umana)"
                )

        if skipped:
            self.stdout.write(self.style.WARNING(
                "\nCasi saltati: " + "; ".join(f"{cid} ({why})" for cid, why in skipped)
            ))

    def _load_gold_case(self, path, strict):
        """Carica un caso gold; con strict=False (gold-all) salta i file illeggibili."""
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError) as e:
            if strict:
                raise CommandError(f"Caso gold non leggibile: {path}: {e}")
            self.stdout.write(self.style.WARNING(f"Caso non leggibile, saltato: {path}: {e}"))
            return None

    def _resolve_case_image(self, case):
        """Risolve l'immagine del caso dai db_report_pk (top-level, poi extractions[]).

        Ritorna (path, report_pk, None) oppure (None, None, motivo).
        Sola lettura sul DB.
        """
        candidates = []
        top_pk = case.get("db_report_pk")
        if top_pk:
            candidates.append(top_pk)
        for entry in case.get("extractions") or []:
            pk = entry.get("db_report_pk")
            if pk and pk not in candidates:
                candidates.append(pk)
        if not candidates:
            return None, None, (
                "nessun db_report_pk nel caso (né top-level né in extractions[])."
            )
        tried = []
        for pk in candidates:
            report = MatchReport.objects.filter(pk=pk).first()
            if report is None:
                tried.append(f"report {pk}: non a DB")
                continue
            if not (report.file and report.file.name):
                tried.append(f"report {pk}: senza file")
                continue
            path = report.file.path
            if not os.path.isfile(path):
                tried.append(f"report {pk}: file mancante su disco ({report.file.name})")
                continue
            return path, pk, None
        return None, None, "nessuna immagine risolvibile — " + "; ".join(tried) + "."

    def _run_models(self, provider, provider_name, models, image_path, preprocess, dump_dir):
        """Esegue l'estrazione per ogni modello e stampa la tabella. Ritorna {model: data}."""
        # Stub minimale: extract_data usa solo .id (logging) e .file.path
        bench_report = SimpleNamespace(
            id=f"bench:{os.path.basename(image_path)}",
            file=SimpleNamespace(path=image_path),
        )

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

        return results

    def _print_show_and_save(self, results, options, case_id=None):
        """Blocchi --show e --save-dir, comuni a modalità classica e gold."""
        if options["show"] and results:
            for model, data in results.items():
                self.stdout.write("")
                for line in build_show_block(model, data):
                    self.stdout.write(line)

        if options["save_dir"] and results:
            save_dir = options["save_dir"]
            os.makedirs(save_dir, exist_ok=True)
            ts = timezone.localtime().strftime("%Y%m%d_%H%M%S")
            # In modalità gold il case_id entra nel nome: evita collisioni
            # tra casi diversi estratti nello stesso secondo.
            prefix = f"ocr_bench_{case_id}__" if case_id else "ocr_bench_"
            self.stdout.write("")
            for model, data in results.items():
                path = os.path.join(
                    save_dir, f"{prefix}{safe_model_slug(model)}_{ts}.json"
                )
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                self.stdout.write(f"Salvato: {path}")

    def _print_gold_comparison(self, case_id, model, fields, inversion):
        """Tabella per-campo del confronto con la truth + check di inversione."""
        self.stdout.write(f"\n--- Confronto con truth: {case_id} — {model} ---")
        header = f"{'campo':<20} {'truth':>18} {'estratto':>18} {'esito':>8} {'confidence':>11}"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))
        for field, row in fields.items():
            conf = row["confidence"]
            conf_str = f"{conf:.2f}" if isinstance(conf, (int, float)) else "N/A"
            extracted = "null" if row["extracted"] is None else str(row["extracted"])
            self.stdout.write(
                f"{field:<20} {str(row['truth']):>18} {extracted:>18} "
                f"{row['verdict']:>8} {conf_str:>11}"
            )

        def fmt(v):
            return {True: "SÌ", False: "no", None: "n/c"}[v]

        q_parts = " ".join(f"Q{k}={fmt(v)}" for k, v in inversion["quarters"].items())
        self.stdout.write(
            "Inversione casa/trasferta: "
            f"finale={fmt(inversion['final_score'])} {q_parts} "
            f"nomi={fmt(inversion['team_names'])}"
            + ("  ← INVERSIONE RILEVATA" if inversion["any"] else "")
        )
        counts = {"correct": 0, "wrong": 0, "null": 0}
        for row in fields.values():
            counts[row["verdict"]] += 1
        self.stdout.write(
            f"Esito campi: {counts['correct']} correct, {counts['wrong']} wrong, "
            f"{counts['null']} null su {len(fields)} confrontati "
            "(null = astensione dichiarata, conteggiata a parte)"
        )
