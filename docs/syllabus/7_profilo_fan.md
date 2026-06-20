## 7. Profilo fan/genitore: follow + certificazione genitore

Stato: ⏳ Da fare

Due tronconi distinti: **7a** il follow (riuso di codice esistente), **7b** la certificazione genitore (nuovo workflow).

### 7a. Follow (riuso `favorite_players`)

- [ ] `FanProfile` 1:1 con `User` (oggi `User.role=fan` non ha profilo dedicato)
- [ ] "Atleti seguiti" = **riuso di `favorite_players`** (M2M self su `User` già a codice, usato in setup wizard e dashboard fan) — infrastruttura disponibile, NON ancora integrata nel FanProfile
- [ ] Tracking "storico partite seguite"
- [ ] Pagina pubblica profilo fan/genitore + sezione atleti seguiti + storico

### 7b. Certificazione genitore (society-vouching) — NUOVO workflow

- [ ] Modello `ParentCertification` con macchina a stati (design in BLUEPRINT §7.7)
- [ ] Email di vouching alla società + match nome+email su gestionale (umano società)
- [ ] Email con link al genitore + endpoint click → attiva accesso dati figlio
- [ ] Gate accesso dati/servizi figlio condizionato a `status=CERTIFICATA`
- [ ] Distinzione netta: follow (7a) ≠ accesso certificato (7b)

---

← [Macro precedente](6_profilo_presidenti.md) | → [Macro successiva](8_ocr_affidabilita.md)
