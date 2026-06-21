## 17. Frontend & Design System

Stato: ⏳ Da fare

Concretizzazione operativa del Cap. 12 del BLUEPRINT: portare tutte le
pagine sotto un'unica direzione estetica, con build e token come fonte
di verità unica. Il "perché" sta nel blueprint; qui stanno gli step.

> Nota: gli step 17.1–17.3 e 17.7 non sono solo-doc quando verranno
> eseguiti — toccheranno `templates/`, `static/` e `tailwind.config`.

### 17.1 Pipeline Tailwind compilata
- [ ] Build Tailwind via CLI/PostCSS con scansione dei template e purge delle classi inutilizzate
- [ ] Rimuovere `cdn.tailwindcss.com` in produzione; CDN ammesso solo in dev locale

### 17.2 Design token centralizzati
- [ ] Spostare colori (navy/slate-950, slate-50, blu di marca, accenti teal/orange/green), spacing, tipografia, raggi e ombre in `tailwind.config`
- [ ] Variabili CSS per i temi
- [ ] Audit ed eliminazione di hex/spacing hardcoded sparsi nei template

### 17.3 Tipografia
- [ ] Caricare Inter (body/dati) + Outfit (titoli)
- [ ] Fix regressione: i titoli restano Outfit in entrambi i temi (no fallback a Inter nel tema chiaro)

### 17.4 Componente stato-vuoto riusabile
- [ ] Componente unico (icona/illustrazione + copy che spiega il perché + CTA opzionale)
- [ ] Applicarlo ovunque il dato possa mancare (classifiche a zero, nessun gol a inizio stagione)

### 17.5 Struttura di pagina
- [ ] Footer reale su tutte le pagine pubbliche
- [ ] Header sticky (logo, nav sport, ricerca, toggle tema)

### 17.6 Dark/light theming
- [ ] Stesso set di token e stessi componenti nei due temi; cambiano solo i valori colore
- [ ] Toggle tema nell'header

### 17.7 Accessibilità base
- [ ] Ogni campo form con `id`/`name` + label associata
- [ ] Navigazione da tastiera e focus visibili

### 17.8 Direzione estetica unica
- [ ] Audit dei template per divergenze view-per-view
- [ ] Allineare tutte le pagine a un'unica direzione estetica

---

← [Macro precedente](16_modello_stagione.md)
