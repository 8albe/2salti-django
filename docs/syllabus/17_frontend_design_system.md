## 17. Frontend & Design System

Stato: ✅ Completata

> Nota stato (2026-06-22): lo scaffolding è **già parziale** in `templates/base.html`
> e `static/css/style.css` — token colore, font Inter+Outfit, `tailwind.config`
> inline letta dal CDN, theme-toggle + `data-theme`, header sticky e footer
> esistono già. La macro **non** parte da zero: l'unico step davvero intatto è
> 17.1 (rimozione CDN + pipeline compilata), fuori da questa pass per scelta.

Concretizzazione operativa del Cap. 12 del BLUEPRINT: portare tutte le
pagine sotto un'unica direzione estetica, con build e token come fonte
di verità unica. Il "perché" sta nel blueprint; qui stanno gli step.

> Nota: gli step 17.1–17.3 e 17.7 non sono solo-doc quando verranno
> eseguiti — toccheranno `templates/`, `static/` e `tailwind.config`.

> Avanzamento (2026-06-22, solo `dev`, HEAD `8ea6e16`, prod invariato
> a `f697c0f`): chiusi e verificati e2e su `dev` (Antigravity, pubbliche +
> login, dark invariato) il blocco tipografia (17.3), il consolidamento
> token in `style.css` — parte CSS-vars dei temi (17.2), il componente
> empty-state (17.4, solo il componente) e la leggibilità del tema chiaro /
> direzione estetica unica (17.8 + 17.8.1). Restano aperti: empty-state
> esteso a classifica/dashboard/profilo + unificazione `sport_detail`
> (17.4), accessibilità base (17.7), footer reale (17.5, previa decisione
> contenuti), token in `tailwind.config` + audit hex hardcoded (17.2,
> gated su 17.1), pipeline compilata e rimozione CDN (17.1, gated sulla
> decisione toolchain/deploy di Alberto). La macro resta 🔄 — è chiuso il
> blocco tema chiaro, non l'intera macro.

> Avanzamento (2026-06-23, solo `dev`, prod invariato a `f697c0f`): chiusi su
> `dev` 17.4 esteso (empty-state su classifica/dashboard/profilo + `sport_detail`),
> 17.7 accessibilità base (label associate + `aria-label` ricerca + `:focus-visible`
> globale) e 17.5 footer reale. CSS a `?v=182`. Verifica e2e (Antigravity) ancora
> da eseguire. Restano aperti 17.1 (pipeline/CDN, gated) e il residuo 17.2
> (`tailwind.config` + audit hex, gated su 17.1). La macro resta 🔄.

> **CHIUSURA Macro 17 (2026-06-30, solo `dev`, prod invariato a `f697c0f`):** Fase 2
> completata — re-skin cromatico Cap. 12 in CSS via token-remap **A1** (`819db21`, literali
> ciano orfani chiusi `ac9b970`) + migration per-sport DB `Sport.hex_color` pallanuoto
> ciano→`#2563eb` applicata su `dev`. Verifica e2e (Antigravity): isole `.dark-surface`
> intatte, zero regressioni WCAG AA; i "residui ciano" segnalati erano falsi positivi
> (classi `cyan-*` che **rendono** blue via `tailwind.config.js`). Resta solo il **debito
> A1** (rinomina classi `cyan-*`→`blue-*`), rimandato al task **A2** futuro non urgente
> (OPS_RUNBOOK §12.9). Tutte le sotto-macro 17.1–17.8.1 chiuse → Macro 17 **✅**.

### 17.1 Pipeline Tailwind compilata
> **Fase 1 (toolchain) — pipeline parziale, su `dev` (2026-06-23):** in piedi `package.json` + `tailwind.config.js` (content glob su template/app `*.py`/JS/crispy + safelist isole `.dark-surface`) + input `static/css/tailwind.src.css`. Il CDN runtime è rimosso da `base.html`, che ora punta a `static/css/tailwind.build.css` compilato e committato (~68KB, purge attivo). Token a **valori invariati** (slate/ciano): nessun cambiamento estetico — il re-skin è Fase 2.
>
> **Fase 1 CHIUSA (2026-06-23):** `ManifestStaticFilesStorage` attivo e verificato (collectstatic post-process di 132 asset, zero errori, fingerprint con hash nel nome). Il cache-busting è ora **automatico**: rimosso il `?v=N` manuale dai link CSS in `base.html` (vedi OPS §12.8/§7.3). La Macro 17 resta 🔄 — manca la **Fase 2** (re-skin Cap. 12: full-palette navy/teal/orange/green, audit hex).
- [x] Build Tailwind via CLI con scansione dei template e purge delle classi inutilizzate (Fase 1, `dev`, e2e in verifica)
- [x] Rimuovere `cdn.tailwindcss.com`; CDN sostituito dal CSS compilato committato (Fase 1, `dev`, e2e in verifica)

### 17.2 Design token centralizzati
> **Fase 1 (2026-06-23):** i token già esistenti (`dark`, `card`, `sport`→`var(--sport-color)`, font Inter/Outfit) sono ora in `tailwind.config.js` a **valori invariati** — chiude il residuo "token in config". La migrazione full-palette (navy/teal/orange/green) e l'audit hex restano **Fase 2**.
>
> **Fase 2 — RE-SKIN CROMATICO APPLICATO (2026-06-23, `dev`, commit `819db21`):** palette Cap. 12 blue+navy. Strategia ratificata = **token-remap (A1)**: la scala `cyan` è schiacciata sui valori `blue` di Tailwind in `tailwind.config.js`, così le ~480 utility `cyan-*` rendono blue **senza rinominare le classi** (niente sweep A2). Perno brand `blue-600 #2563eb`. `style.css`: accent/glow/neon → blue, accento secondario radiale → teal, nav-link tema chiaro `#0e7490`→`#1d4ed8` (blue-700 AA), fallback focus ring → `#2563eb`. `base.html`: `--sport-color` fallback → `#2563eb`, selection → blue-500, CTA gradient anti-appiattimento. Funzionali green/orange/teal/red = già default Tailwind, invariati. Build ribuildata (~68KB), suite **417 verde**. **Solo cromatico** (tipografia/raggi/spacing/layout invariati).
>
> ⚠️ **Residui aperti Fase 2** (la Macro resta 🔄): (a) **per-sport color DB-driven** (`Sport.hex_color`): codice pronto su `dev` (commit `e5eab0d`) — model default `#00ffff`→`#2563eb` (schema migration `0020`), data migration `0021` difensiva (solo `slug='pallanuoto'`, idempotente, reversibile), seed allineato. **CHIUSO (2026-06-30):** migration `0020`/`0021` applicata su `dev` e **propagata a prod** (deploy `24bfc62`) — `0021` data-migration ha toccato 1 row, pallanuoto su prod ora `#2563eb`. Il residuo "gated da backup+ratifica" è **chiuso**; (b) **literali ciano orfani** (`rgba(6,182,212,…)` glow + hex `#0891b2`/`#0e7490`/fallback `#06b6d4`) — CHIUSO su `dev` (commit `ac9b970`): 15 template portati a blue-600, grep literali ciano = 0; (c) **verifica e2e Antigravity** (dark+light, tutte le superfici, + ri-verifica sport-context post-migration) ancora da eseguire; (d) **debito semantico A1** (classi `cyan-*` che rendono blue) → vedi OPS_RUNBOOK §12.9.
- [x] Migrare la palette di marca (blu+navy) in `tailwind.config` via token-remap della scala cyan — _(Fase 2, 2026-06-23, `dev`)_
- [x] Variabili CSS per i temi — consolidate in `style.css` (2026-06-22, `dev`)
- [x] Audit ed eliminazione di hex/spacing hardcoded sparsi nei template — _(literali ciano orfani chiusi: 15 template → blue-600, grep=0, 2026-06-30, `dev`, `ac9b970`; resta solo il debito A1 nomi-classe `cyan-*`, voluto)_
- [x] Cambio DB `Sport.hex_color` pallanuoto ciano→blue — _(model+migration `0020`/`0021`+seed, `e5eab0d`; migration applicata su `dev` e **propagata a prod** 2026-06-30, deploy `24bfc62`; pallanuoto prod = `#2563eb`)_

### 17.3 Tipografia
- [x] Caricare Inter (body/dati) + Outfit (titoli)
- [x] Fix regressione: i titoli restano Outfit in entrambi i temi (no fallback a Inter nel tema chiaro) — chiuso e verificato e2e (2026-06-22, `dev`)

### 17.4 Componente stato-vuoto riusabile
- [x] Componente unico (icona/illustrazione + copy che spiega il perché + CTA opzionale) — `templates/components/_empty_state.html` (2026-06-22, `dev`)
- [x] Applicarlo ovunque il dato possa mancare (classifiche a zero, nessun gol a inizio stagione) — esteso a classifica (`league_standings`), dashboard, profilo e unificato `sport_detail` (2026-06-23, `dev`, e2e in verifica)

### 17.5 Struttura di pagina
- [x] Footer reale su tutte le pagine pubbliche — wordmark + tagline, link prodotto (Partite/Classifiche/Statistiche su route reali, primo rollout Pallanuoto), contatto mailto, riga © + Beta; "Società" escluso (nessun hub pubblico) (2026-06-23, `dev`, e2e in verifica)
- [x] Header sticky (logo, nav sport, ricerca, toggle tema) — già presente nello scaffolding `base.html`

### 17.6 Dark/light theming
- [x] Stesso set di token e stessi componenti nei due temi; cambiano solo i valori colore — token consolidati in `style.css`/`tailwind.config.js` (17.2) + isole `.dark-surface` verificate (17.8.1)
- [x] Toggle tema nell'header — `data-theme` + theme-toggle già nello scaffolding `base.html`

### 17.7 Accessibilità base
- [x] Ogni campo form con `id`/`name` + label associata — `for=`/`id` su setup_wizard, request_certification, generate_code; `aria-label` sui 3 input di ricerca in `base.html`; login/signup già via crispy (2026-06-23, `dev`, e2e in verifica)
- [x] Navigazione da tastiera e focus visibili — regola globale `:focus-visible` in `style.css` (anello keyboard-only, vince sul reset outline del CDN Tailwind) (2026-06-23, `dev`, e2e in verifica)

### 17.8 Direzione estetica unica
- [x] Audit dei template per divergenze view-per-view — chiuso e verificato e2e (2026-06-22, `dev`)
- [x] Allineare tutte le pagine a un'unica direzione estetica — leggibilità tema chiaro chiusa, dark invariato (2026-06-22, `dev`)

#### 17.8.1 Leggibilità tema chiaro
- [x] Isole scure marcate `.dark-surface` (fix container-keyed); `<select>` glass `bg-slate-900/50` trattati come isole (fondo chiaro + testo scuro); chip annidati, nav header/sidebar e input navbar leggibili nel chiaro — chiuso e verificato e2e (2026-06-22, `dev`, CSS `?v=179`)

---

← [Macro precedente](16_modello_stagione.md)
