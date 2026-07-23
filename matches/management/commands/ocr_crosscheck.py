"""
Cross-check Pro↔Flash sulle proposte del bench OCR (Macro 8, §8.20), read-only.

Consuma due directory di proposte `ocr_bench --repeat N` (un braccio per
modello) e stampa: gli assi §8.19 per braccio (asse a + errori stabili noti +
eventi referto 8) e il cross-check per campo col gold come verità
(concordi/discordi, recall del disaccordo come predittore d'errore, tasso
concordi-e-sbagliati). Nessuna chiamata reale: pura analisi dei JSON già
prodotti. La logica vive in matches/services/ocr_bench_analysis.py (versionata:
la lezione di §8.19 è che una misura senza strumento a repo non è ripetibile).
"""
import json
import os

from django.core.management.base import BaseCommand, CommandError

from matches.services import ocr_bench_analysis as A


class Command(BaseCommand):
    help = (
        "Cross-check Pro↔Flash sulle proposte del bench OCR (read-only). "
        "Uso: ocr_crosscheck --pro-dir <dir> --flash-dir <dir> "
        "[--pro-model gemini-2.5-pro] [--flash-model gemini-3.6-flash] [--save-json <path>]"
    )

    def add_arguments(self, parser):
        parser.add_argument("--pro-dir", required=True, help="Directory proposte braccio Pro")
        parser.add_argument("--flash-dir", required=True, help="Directory proposte braccio Flash")
        parser.add_argument("--pro-model", default="gemini-2.5-pro", help="Slug modello Pro nei nomi file")
        parser.add_argument("--flash-model", default="gemini-3.6-flash", help="Slug modello Flash nei nomi file")
        parser.add_argument("--save-json", default=None, help="Salva il report completo in questo path")

    def handle(self, *args, **options):
        for key in ("pro_dir", "flash_dir"):
            if not os.path.isdir(options[key]):
                raise CommandError(f"Directory non trovata: {options[key]}")

        pro = A.load_arm(options["pro_dir"], options["pro_model"])
        flash = A.load_arm(options["flash_dir"], options["flash_model"])
        if not pro:
            raise CommandError(f"Nessuna proposta '{options['pro_model']}' in {options['pro_dir']}")
        if not flash:
            raise CommandError(f"Nessuna proposta '{options['flash_model']}' in {options['flash_dir']}")

        self.stdout.write(f"Pro:   {len(pro)} casi ({options['pro_model']})")
        self.stdout.write(f"Flash: {len(flash)} casi ({options['flash_model']})")

        # --- Asse a per braccio ---
        a_pro = A.axis_a(pro.values())
        a_flash = A.axis_a(flash.values())
        self.stdout.write("\n=== Asse a (punteggi/parziali/data + nomi) ===")
        self.stdout.write(
            f"{'braccio':<22}{'n':>4}{'sc':>5}{'sw':>5}{'null':>6}{'inst':>6}{'amb':>5}"
        )
        for label, a in (("Pro (2.5-pro)", a_pro), ("Flash (3.6-flash)", a_flash)):
            self.stdout.write(
                f"{label:<22}{a['n_fields']:>4}{a['stable_correct']:>5}{a['stable_wrong']:>5}"
                f"{a['stable_null']:>6}{a['instabile']:>6}{a['ambiguo']:>5}"
            )

        # --- Cross-check ---
        buckets, metrics, rows = A.crosscheck_fields(pro, flash)
        self.stdout.write("\n=== Cross-check Pro↔Flash (campi punteggi/parziali/data/nomi) ===")
        self.stdout.write(f"  comparabili: {metrics['comparable_fields']} "
                          f"(esclusi null su un braccio: {metrics['excluded_null_fields']})")
        self.stdout.write(f"  concordi-e-giusti:            {buckets['concordi_giusti']}")
        self.stdout.write(f"  concordi-e-SBAGLIATI (cieco): {buckets['concordi_sbagliati']}")
        self.stdout.write(f"  discordi-uno-giusto:          {buckets['discordi_uno_giusto']}")
        self.stdout.write(f"  discordi-entrambi-sbagliati:  {buckets['discordi_entrambi_sbagliati']}")

        def pct(x):
            return "N/A" if x is None else f"{x*100:.1f}%"

        self.stdout.write("\n  Disaccordo come predittore d'errore (unione dei due bracci):")
        self.stdout.write(f"    error_fields:     {metrics['error_fields']}")
        self.stdout.write(f"    recall_union:     {pct(metrics['recall_union'])} "
                          f"(errori catturati dal disaccordo)")
        self.stdout.write(f"    blind_rate_union: {pct(metrics['blind_rate_union'])} "
                          f"(concordi-e-sbagliati / error_fields)")
        self.stdout.write(f"    precision_union:  {pct(metrics['precision_union'])} "
                          f"(1.0 per costruzione)")
        self.stdout.write(f"    tasso concordi-e-sbagliati / comparabili: "
                          f"{pct(metrics['concordi_sbagliati_rate'])}")
        self.stdout.write("\n  Prospettiva produzione (errori del braccio Pro):")
        self.stdout.write(f"    pro_error_fields: {metrics['pro_error_fields']}")
        self.stdout.write(f"    recall_pro:       {pct(metrics['recall_pro'])} "
                          f"(errori Pro catturati); missed (ciechi): {metrics['missed_pro']}")

        # --- Righe errori stabili noti ---
        self.stdout.write("\n=== Errori stabili noti (Bellator finale casa, Triscelon data) ===")
        known = A.known_stable_error_rows(rows)
        if not known:
            self.stdout.write("  (nessuna delle due righe presente nei casi comuni)")
        for r in known:
            self.stdout.write(
                f"  {r['case_id'][:28]:<28} {r['field']:<17} truth={r['truth']!r}\n"
                f"      Pro   -> {r['pro']!r} (stabile={r['pro_stable']}, giusto={r['pro_correct']})\n"
                f"      Flash -> {r['flash']!r} (stabile={r['flash_stable']}, giusto={r['flash_correct']})\n"
                f"      => {'CONCORDI' if r['agree'] else 'DISCORDI'} [{r['class']}]"
            )

        # --- Eventi referto 8 (asse b/g) ---
        self.stdout.write("\n=== Eventi referto 8 (Unime) per ripetizione ===")
        for label, arm in (("Pro", pro), ("Flash", flash)):
            ev = A.events_referto8(arm)
            if ev is None:
                self.stdout.write(f"  {label}: caso referto 8 assente")
                continue
            gt = [e["goals_total"] for e in ev]
            ga = [e["goals_with_author"] for e in ev]
            to = [e["timeouts"] for e in ev]
            ed = [e["edcs"] for e in ev]
            self.stdout.write(f"  {label}: gol_tot={gt} (truth 22) con_autore={ga} "
                              f"timeout={to} (truth 3) edcs={ed} (truth 1)")

        if options["save_json"]:
            report = {
                "axis_a": {"pro": a_pro, "flash": a_flash},
                "crosscheck": {"buckets": buckets, "metrics": metrics, "rows": rows},
                "events_referto8": {
                    "pro": A.events_referto8(pro), "flash": A.events_referto8(flash),
                },
            }
            with open(options["save_json"], "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            self.stdout.write(f"\nReport salvato: {options['save_json']}")
