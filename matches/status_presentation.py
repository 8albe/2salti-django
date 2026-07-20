"""
Presentazione unica degli stati di `MatchReport` (Macro 22, giro 2).

Perche' questo modulo esiste: l'introduzione dello stato `QUEUED` ha rotto 7
punti su 14 che enumeravano gli stati a mano — cinque catene `{% if %}` nei
template, il dizionario colori dell'admin, i bucket KPI del cockpit. Ognuna
era una lista chiusa scritta a mano, e nessuna falliva quando un nuovo stato
non vi compariva: cadeva semplicemente nel ramo `{% else %}` grigio.

La regola ora e' una sola: **nessuna enumerazione di stati fuori da qui**.
Chi deve colorare un badge passa da `tone_for()` / dal filtro `status_classes`;
chi deve contare passa da `bucket_for()`. I test in
`matches/tests_status_coverage.py` derivano la checklist da `Status.choices`,
quindi un decimo stato aggiunto domani fa fallire la suite finche' non e'
classificato qui — che e' esattamente il segnale mancato a luglio.

Il mapping e' su un *tono semantico* e non direttamente su classi CSS: i badge
vivono su fondo scuro (coda referti), su fondo chiaro (cockpit staff), come
pallino colorato (dettaglio partita) e come colore CSS piatto (admin Django).
Un solo mapping stato->tono, N palette tono->classi: aggiungere un tema non
richiede di ritoccare gli stati, e aggiungere uno stato non richiede di
ritoccare i temi.
"""
from matches.models import MatchReport

Status = MatchReport.Status


# --- toni semantici ---------------------------------------------------------
# Il tono dice *cosa significa operativamente* lo stato, non che colore ha.
NEUTRAL = 'neutral'      # non ancora nel flusso (bozza)
PENDING = 'pending'      # ricevuto, non ancora preso in carico
PROGRESS = 'progress'    # in mano alla pipeline OCR, si muove da solo
INFO = 'info'            # richiede un occhio umano, nessun problema
READY = 'ready'          # approvato, manca solo la pubblicazione
DONE = 'done'            # terminale positivo
ATTENTION = 'attention'  # terminale che richiede intervento tecnico
DANGER = 'danger'        # terminale negativo

TONE_BY_STATUS = {
    Status.DRAFT: NEUTRAL,
    Status.UPLOADED: PENDING,
    Status.QUEUED: PROGRESS,
    Status.PROCESSING: PROGRESS,
    Status.EXTRACTED: INFO,
    Status.VALIDATED: READY,
    Status.PUBLISHED: DONE,
    Status.NEEDS_REVIEW: ATTENTION,
    Status.REJECTED: DANGER,
}

TONES = (NEUTRAL, PENDING, PROGRESS, INFO, READY, DONE, ATTENTION, DANGER)


# --- palette per tema -------------------------------------------------------
# 'dark'  = badge su fondo scuro   (matches/report_queue.html)
# 'light' = badge su fondo chiaro  (management/ops_cockpit.html)
# 'dot'   = pallino colorato       (matches/match_detail.html)
# 'border'= bordo sinistro card    (management/staff_dashboard.html)
# 'admin' = colore CSS piatto      (matches/admin.py, format_html)
PALETTES = {
    'dark': {
        NEUTRAL: 'bg-slate-800 text-slate-400',
        PENDING: 'bg-amber-500/20 text-amber-400',
        PROGRESS: 'bg-indigo-500/20 text-indigo-400',
        INFO: 'bg-blue-500/20 text-blue-400',
        READY: 'bg-green-500/20 text-green-400',
        DONE: 'bg-emerald-500/20 text-emerald-400',
        ATTENTION: 'bg-orange-500/20 text-orange-400',
        DANGER: 'bg-rose-500/20 text-rose-400',
    },
    'light': {
        NEUTRAL: 'bg-slate-100 text-slate-600',
        PENDING: 'bg-amber-100 text-amber-700',
        PROGRESS: 'bg-indigo-100 text-indigo-700',
        INFO: 'bg-blue-100 text-blue-700',
        READY: 'bg-green-100 text-green-700',
        DONE: 'bg-emerald-100 text-emerald-700',
        ATTENTION: 'bg-orange-100 text-orange-700',
        DANGER: 'bg-rose-100 text-rose-700',
    },
    'dot': {
        NEUTRAL: 'bg-slate-500',
        PENDING: 'bg-amber-500 animate-pulse',
        PROGRESS: 'bg-indigo-500 animate-pulse',
        INFO: 'bg-blue-500',
        READY: 'bg-green-500',
        DONE: 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]',
        ATTENTION: 'bg-orange-500',
        DANGER: 'bg-rose-500',
    },
    'border': {
        NEUTRAL: 'border-slate-400',
        PENDING: 'border-amber-500',
        PROGRESS: 'border-indigo-500',
        INFO: 'border-blue-500',
        READY: 'border-green-500',
        DONE: 'border-emerald-500',
        ATTENTION: 'border-orange-500',
        DANGER: 'border-rose-500',
    },
    'admin': {
        NEUTRAL: 'gray',
        PENDING: 'goldenrod',
        PROGRESS: 'purple',
        INFO: 'blue',
        READY: 'green',
        DONE: 'darkgreen',
        ATTENTION: 'red',
        DANGER: 'black',
    },
}


# --- bucket operativi -------------------------------------------------------
# Partizione TOTALE e DISGIUNTA degli stati: ogni referto sta in esattamente un
# bucket. E' cosi' che i KPI del cockpit smettono di perdere pezzi per strada —
# prima DRAFT non era contato da nessuna delle cinque metriche, quindi un
# referto digitale abbandonato in bozza era invisibile allo staff.
BUCKET_DRAFT = 'draft'
BUCKET_IN_FLIGHT = 'in_flight'
BUCKET_PENDING_REVIEW = 'pending_review'
BUCKET_NEEDS_REVIEW = 'needs_review'
BUCKET_FAILED = 'failed'
BUCKET_DONE = 'done'

BUCKETS = {
    BUCKET_DRAFT: (Status.DRAFT,),
    BUCKET_IN_FLIGHT: (Status.UPLOADED, Status.QUEUED, Status.PROCESSING),
    BUCKET_PENDING_REVIEW: (Status.EXTRACTED, Status.VALIDATED),
    BUCKET_NEEDS_REVIEW: (Status.NEEDS_REVIEW,),
    BUCKET_FAILED: (Status.REJECTED,),
    BUCKET_DONE: (Status.PUBLISHED,),
}

# Stati terminali: il referto non si muovera' piu' da solo.
TERMINAL_STATUSES = frozenset({Status.PUBLISHED, Status.REJECTED, Status.NEEDS_REVIEW})

# Stati "chiusi": la pratica e' finita e non c'e' lavoro residuo per nessuno.
# Attenzione: NEEDS_REVIEW e' terminale per la *pipeline* (nessun retry) ma NON
# e' chiuso, perche' resta lavoro umano. Le due nozioni non coincidono e
# confonderle e' esattamente il modo in cui un referto sparisce dai radar.
SETTLED_STATUSES = frozenset({Status.PUBLISHED, Status.REJECTED})

# Complemento di SETTLED_STATUSES: tutto cio' su cui qualcuno deve ancora fare
# qualcosa. Derivato, non scritto a mano.
OPEN_STATUSES = frozenset(s for s, _ in Status.choices) - SETTLED_STATUSES

# Stati in cui il referto e' in mano al worker OCR e avanzera' senza intervento.
# Unica fonte per il polling dell'endpoint di stato (`is_final`).
PIPELINE_STATUSES = frozenset({Status.QUEUED, Status.PROCESSING})


def tone_for(status):
    """Tono semantico di uno stato. Solleva KeyError su uno stato non mappato."""
    return TONE_BY_STATUS[status]


def classes_for(status, theme='dark'):
    """Classi CSS del badge per (stato, tema)."""
    return PALETTES[theme][tone_for(status)]


def bucket_for(status):
    """Bucket operativo di uno stato. Solleva KeyError se non classificato."""
    for bucket, members in BUCKETS.items():
        if status in members:
            return bucket
    raise KeyError(f"Stato {status!r} non assegnato ad alcun bucket operativo")
