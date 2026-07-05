## 7. Profilo fan/genitore: follow + certificazione genitore

Stato: 🔄 In corso — 7a + 7b implementati su dev; "storico partite seguite" differito

Due tronconi distinti: **7a** il follow (riuso di codice esistente), **7b** la certificazione genitore (nuovo workflow).

### 7a. Follow (riuso `favorite_players`)

- [x] `FanProfile` 1:1 con `User` (oggi `User.role=fan` non ha profilo dedicato)
- [x] "Atleti seguiti" = **riuso di `favorite_players`** (M2M self su `User` già a codice, usato in setup wizard e dashboard fan) — multi-follow integrato nel FanProfile
- [ ] Tracking "storico partite seguite"
- [x] Pagina pubblica profilo fan/genitore + sezione atleti seguiti (storico differito)

### 7b. Certificazione genitore (society-vouching) — NUOVO workflow

- [x] Modello `ParentCertification` con macchina a stati (design in BLUEPRINT §7.7)
- [x] Email di vouching alla società + match nome+email su gestionale (umano società)
- [x] Email con link al genitore + endpoint click → attiva accesso dati figlio
- [ ] Gate accesso dati/servizi figlio condizionato a `status=CERTIFICATA` — helper `User.is_certified_parent_of()` presente e testato (`accounts/models.py:131`), ma non ancora cablato in nessuna view/template
- [x] Distinzione netta: follow (7a) ≠ accesso certificato (7b)

---

← [Macro precedente](6_profilo_presidenti.md) | → [Macro successiva](8_ocr_affidabilita.md)
