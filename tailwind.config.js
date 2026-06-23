/**
 * Tailwind CSS v3 config — 2salti (Macro 17.1 Fase 1).
 *
 * Replaces the runtime Play CDN (cdn.tailwindcss.com) with a committed,
 * compiled build. PHASE 1 = toolchain only: the tokens below carry the
 * SAME values that were inlined in base.html's CDN config — no colour change.
 * The chromatic re-skin (Cap. 12 palette) is Phase 2.
 *
 * `content` must list EVERY place a Tailwind class can appear, or the JIT
 * purge silently drops unseen utilities. Beyond our templates that means:
 *   - inline <script> blocks (JS classList.add('text-green-400', ...)) — these
 *     live inside the .html files, so the template glob already covers them;
 *   - widget class strings in our forms.py (e.g. matches/forms.py);
 *   - crispy-tailwind's OWN package templates, which render the login/signup
 *     form classes (border-gray-300, rounded-lg, ...). With the CDN these were
 *     caught by the browser at runtime; the compiled build must scan them here.
 *
 * The build runs ONLY on a dev machine with node (this repo's npm scripts);
 * the dev/prod boxes just `collectstatic` the committed tailwind.build.css.
 */
module.exports = {
  content: [
    './templates/**/*.html',
    './static/js/**/*.js',
    // Tailwind class strings embedded in Python widget attrs (forms.py et al.)
    './accounts/**/*.py',
    './core/**/*.py',
    './matches/**/*.py',
    './management/**/*.py',
    './seasons/**/*.py',
    './config/**/*.py',
    // crispy-tailwind renders form-field classes from its own package templates.
    // Path is venv-version-specific (python3.12); update if the venv moves.
    './.venv/lib/python3.12/site-packages/crispy_forms/templates/**/*.html',
    './.venv/lib/python3.12/site-packages/crispy_tailwind/templates/**/*.html',
  ],
  // Safelist = utilities that exist ONLY inside style.css descendant selectors
  // (the light-theme ".dark-surface" islands, 17.3/17.4 work). They are applied
  // to real elements, but to be safe against any element whose literal token the
  // scanner might miss we pin them. Values unchanged — Phase 1 is colour-neutral.
  safelist: [
    'text-white',
    'text-slate-100',
    'text-slate-200',
    'text-slate-300',
    'text-slate-400',
    'text-gray-300',
    'text-gray-400',
    'hover:text-white',
    'group-hover:text-white',
  ],
  theme: {
    extend: {
      // Same tokens that were inlined in base.html's CDN tailwind.config.
      // `sport` was Django-rendered per page in the CDN config; here it maps to
      // the --sport-color CSS var that base.html still sets inline per sport, so
      // text-sport / bg-sport / border-sport stay per-sport and visually identical.
      colors: {
        dark: '#020617',
        card: 'rgba(15, 23, 42, 0.8)',
        sport: 'var(--sport-color)',
        // Macro 17 Fase 2 — RE-SKIN CROMATICO Cap. 12 (token-remap, strategia A1).
        // La scala `cyan` viene schiacciata sui valori `blue` di Tailwind: le ~480
        // utility cyan-* esistenti nei template rendono BLUE senza rinominare le
        // classi (niente find-replace A2 sui template). Perno brand = blue-600.
        // DEBITO SEMANTICO NOTO: i template chiamano ancora `cyan-*` ma rendono blue;
        // la ripulitura dei nomi classe (cyan-*->blue-*) e' un task A2 futuro.
        // `sky` NON e' usato in nessun template -> non rimappato. I funzionali
        // (green/orange/teal/red) sono gia' i default Tailwind ratificati -> invariati.
        cyan: {
          50: '#eff6ff', 100: '#dbeafe', 200: '#bfdbfe', 300: '#93c5fd',
          400: '#60a5fa', 500: '#3b82f6', 600: '#2563eb', 700: '#1d4ed8',
          800: '#1e40af', 900: '#1e3a8a', 950: '#172554',
        },
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        display: ['Outfit', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
