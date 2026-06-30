## 9. Sistema sponsor

Stato: 🔄 In corso

Sponsor associati a società/campionati, visualizzazione pubblica, modello dati dedicato (non solo JSONField).

### 9.1 Modello dati

- [x] `Society.sponsors` come `JSONField` flat (`[{"name", "logo_url"}]`) — **legacy deprecato**, lasciato intatto (vuoto su dev; stato prod non verificato → nessuna data-migration cieca)
- [x] Modello `core.Sponsor` relazionale separato (FK Society + FK Season; campi `name`, `logo_url` URLField, `url`, `order`, `is_active`) — migration `0022_sponsor`
- [x] Targeting per stagione (società-wide, render sulla stagione corrente via `core.services.sponsor_service.get_society_sponsors`)
- [x] Placement: pagina società (forma piena) + profilo atleta del club (forma ridotta). **Footer: fuori scope di questo giro.**
- [x] Test serializzazione/targeting sponsor (`core/tests_sponsor.py`, 14 test)

### 9.2 Visualizzazione pubblica

- [x] Render sponsor su pagina società (forma piena, link esterno `rel="sponsored noopener nofollow"`, degradazione a zero pulita)
- [x] Render sponsor su profilo atleta del club (forma ridotta, stessa degradazione)
- [ ] Render su footer (non previsto in Macro 9)

### 9.3 Gestione e dati (stato pilota)

- [x] CRUD seed/admin-only: modello registrato su `op_admin_site` + default admin
- [ ] UI gestione sponsor lato Club Pro/Dirigente — **differita** (fuori scope: pilota seed/admin-only)
- [ ] Dati reali Zero9 — da seedare (script `seed_zero9_sponsors_DRAFT.py`, untracked; lancio + dati reali lato Alberto)

**As-built (2026-06-30):** modulo sponsor relazionale completo su `dev` salvo UI CRUD e dati reali Zero9. Solo Zero9 avrà sponsor nel pilota; le altre società degradano a zero senza placeholder rotti.

---

← [Macro precedente](8_ocr_affidabilita.md) | → [Macro successiva](10_subscription_piani.md)
