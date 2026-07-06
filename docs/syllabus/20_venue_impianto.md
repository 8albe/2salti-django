## 20. Modello Venue / Impianto

Stato: ❌ Rimossa dallo scope (decisione di prodotto 2026-07-06 — NON è in roadmap differita: rientra SOLO su decisione manuale esplicita di Alberto. Questa macro è la scheda di dettaglio tecnico; storico del parcheggio in [FUTURE_IDEAS.md](../FUTURE_IDEAS.md) §1)

Promozione dell'impianto sportivo (piscina/palazzetto) a entità di prima classe: modello `Venue` con FK da `Match`, per aggregare partite per impianto, profilarli (indirizzo, mappa, note logistiche) e navigare per luogo.

### 20.1 As-is

Oggi il luogo della partita è **stringa libera**: `Match.location`, `CharField(max_length=200, blank=True)` ([matches/models.py:17](../../matches/models.py)), con link Google Maps generato dalla stringa (`Match.get_maps_link`). Nessuna entità impianto, nessuna aggregazione per luogo. È l'unica voce del parcheggio FUTURE_IDEAS §1 che comporterebbe schema-change e migration.

### 20.2 Condizione di rientro in scope

Rientra in scope SOLO su decisione manuale esplicita di Alberto — nessun trigger automatico di roadmap. Un eventuale dato reale sui luoghi (import calendario FIN che espone gli impianti, dati impianto dalla collaborazione Zero9) è al più l'occasione per porsi la domanda, non una condizione che riattiva la macro da sola. Fino ad allora fuori scope: il luogo resta stringa libera (`Match.location`).

### 20.3 Relazione con la Macro 3

Il modello Venue era **l'unico residuo aperto** della [Macro 3 — Pagina pubblica della classifica](3_pagina_pubblica_classifica.md) (✅ chiusa), già rimandato "a quando serviranno dati reali" e poi parcheggiato con la potatura 2026-07. Questa macro ne eredita il residuo: la Macro 3 resta chiusa e rimanda qui.

### 20.4 Scope di massima, se mai riaperta

- [ ] Modello `Venue` (nome, indirizzo, città, note) + migration
- [ ] FK `Match.venue` con backfill/riconciliazione delle stringhe `Match.location` esistenti (la stringa libera resta come fallback)
- [ ] Pagina/aggregazione partite per impianto
- [ ] Fonte dati: mapping dall'import calendario FIN o dai dati reali Zero9 (a seconda del trigger che scatta)

---

← [Macro precedente](19_monetizzazione_stripe.md)
