## 14. Referto digitale mobile (Jury App)

Stato: 🧊 Differito

App/interfaccia mobile per arbitri/giuria. Jury Tokens, firma PIN, offline-first. Convergenza JSON con OCR su `schema_version: 2.0`.

> **Differimento (2026-06-02):** le decisioni di prodotto sono complete (vedi §14.1–14.3). L'implementazione è rinviata perché bloccata sull'accordo/integrazione federale per l'emissione dei Jury Token (issuer = federazione/lega), oggi non disponibile.
> È una dipendenza esterna reale, non un rinvio di comodo: senza l'autorità emittente non è progettabile il flusso di certificazione.

### 14.1 Ruolo e identità giuria

- [x] **Decisione PRESA:** nuovo valore enum `jury` in `User.role` (NON sotto-ruolo di referee). Allineato a BLUEPRINT §7.1 ("Giuria (Cert)" è già ruolo distinto).
- [ ] Migrazione DB additiva (nessun backfill utenti esistenti) — *implementazione differita*

### 14.2 Jury Tokens

- [ ] Modello `JuryToken` (match-specific, `user_id` + `match_id`)
- [ ] Finestra validità 30 min pre-match
- [ ] Revoca automatica al fischio finale
- [ ] Revoca manuale admin
- [ ] Endpoint emissione token `POST /api/jury/token/issue`
- [x] **Decisione PRESA:** issuer token = **federazione/lega** (NON club). Conferma BLUEPRINT §7.4.1 e §13. Implementazione differita: dipende dall'accordo federale (vedi nota differimento sopra).

### 14.3 Form Referto Digitale mobile

- [x] Workflow `DRAFT → VALIDATED → PUBLISHED` per `source_channel=DIGITAL` (vedi macro 8 §8.3, STATE_MACHINES.md §1)
  - ⚠️ *Nota aperta (doc-vs-codice), da verificare in fase implementativa:* il workflow è marcato fatto, ma `api_views_digital.py::api_digital_report_close` chiude il referto digitale in `NEEDS_REVIEW` (coda review), non direttamente in VALIDATED/PUBLISHED.
- [x] REST CRUD draft digitale in `api_views_digital.py` + routing `api_urls.py`
- [ ] UI mobile compilazione referto (Base + Avanzato)
- [ ] Sync offline-first (Service Worker + IndexedDB)
- [x] **Decisione PRESA:** conflict resolution = **single-writer lock per match** (NON last-write-wins, NON merge field-level). Handover-on-failure = dettaglio implementativo aperto, da definire in fase implementazione.

### 14.4 Firma arbitro

- [ ] Firma PIN arbitro a fine gara
- [ ] Immutabilità referto firmato (hash/lock sul `MatchReport`)
- [ ] Correzioni post-firma solo via admin con audit log completo

---

← [Macro precedente](13_season_archive.md) | → [Macro successiva](15_stabilita_tecnica.md)
