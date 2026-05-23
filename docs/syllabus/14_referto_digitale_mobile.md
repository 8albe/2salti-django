## 14. Referto digitale mobile (Jury App)

Stato: ⏳ Da fare

App/interfaccia mobile per arbitri/giuria. Jury Tokens, firma PIN, offline-first. Convergenza JSON con OCR su `schema_version: 2.0`.

### 14.1 Ruolo e identità giuria

- [ ] Decisione: aggiungere `jury` all'enum `User.role` (oggi: athlete/coach/referee/fan/president) oppure sotto-ruolo di referee
- [ ] Migrazione DB e backfill utenti esistenti

### 14.2 Jury Tokens

- [ ] Modello `JuryToken` (match-specific, `user_id` + `match_id`)
- [ ] Finestra validità 30 min pre-match
- [ ] Revoca automatica al fischio finale
- [ ] Revoca manuale admin
- [ ] Endpoint emissione token `POST /api/jury/token/issue`
- [ ] Decisione "chi emette" — federazione, lega o club (pendente, bloccante)

### 14.3 Form Referto Digitale mobile

- [ ] UI mobile compilazione referto (Base + Avanzato)
- [ ] Sync offline-first
- [ ] Conflict resolution sync multi-device (policy pendente)

### 14.4 Firma arbitro

- [ ] Firma PIN arbitro a fine gara
- [ ] Immutabilità referto firmato (hash/lock sul `MatchReport`)
- [ ] Correzioni post-firma solo via admin con audit log completo

---

← [Macro precedente](13_season_archive.md) | → [Macro successiva](15_stabilita_tecnica.md)
