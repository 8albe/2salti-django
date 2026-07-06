## 20. Modello Venue / Impianto

Stato: 🧊 Differita (per decisione di prodotto 2026-07-06 — rientra in roadmap dalla voce parcheggiata in FUTURE_IDEAS §1, ora con macro dedicata e trigger esplicito)

Promozione dell'impianto sportivo (piscina/palazzetto) a entità di prima classe: modello `Venue` con FK da `Match`, per aggregare partite per impianto, profilarli (indirizzo, mappa, note logistiche) e navigare per luogo.

### 20.1 As-is

Oggi il luogo della partita è **stringa libera**: `Match.location`, `CharField(max_length=200, blank=True)` ([matches/models.py:17](../../matches/models.py)), con link Google Maps generato dalla stringa (`Match.get_maps_link`). Nessuna entità impianto, nessuna aggregazione per luogo. È l'unica voce dell'ex-parcheggio FUTURE_IDEAS §1 che comporterebbe schema-change e migration.

### 20.2 Trigger di attivazione

Si costruisce quando arriva dato reale sui luoghi da popolare — import calendario FIN che espone gli impianti, oppure dati impianto reali dalla collaborazione Zero9. Fino ad allora il luogo resta stringa libera.

### 20.3 Relazione con la Macro 3

Il modello Venue era **l'unico residuo aperto** della [Macro 3 — Pagina pubblica della classifica](3_pagina_pubblica_classifica.md) (✅ chiusa), già rimandato "a quando serviranno dati reali" e poi parcheggiato con la potatura 2026-07. Questa macro ne eredita il residuo: la Macro 3 resta chiusa e rimanda qui.

### 20.4 Scope di massima all'accensione

- [ ] Modello `Venue` (nome, indirizzo, città, note) + migration
- [ ] FK `Match.venue` con backfill/riconciliazione delle stringhe `Match.location` esistenti (la stringa libera resta come fallback)
- [ ] Pagina/aggregazione partite per impianto
- [ ] Fonte dati: mapping dall'import calendario FIN o dai dati reali Zero9 (a seconda del trigger che scatta)

---

← [Macro precedente](19_monetizzazione_stripe.md)
