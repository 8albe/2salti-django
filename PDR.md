# PDR — 1x2 Codex: Bug Fix & Feature Sprint
**Data**: 21/02/2026  
**Metodo**: Ralph Loop (una task alla volta, revisione PDR tra ogni task)

---

## TASK 1 — Fix: Pulsante Logout non funziona

**Problema**: Il logout in Django 5+ richiede una richiesta POST per motivi di sicurezza (CSRF). Il template usa un `<a href>` (GET), quindi il logout non viene eseguito.

**Soluzione**:
- Sostituire il link `<a href="logout">` nel `base.html` con un mini-form `<form method="POST">` con token CSRF.
- Da fare sia nella sidebar desktop che nel menu mobile overlay.

**File da modificare**:
- `templates/base.html`

---

## TASK 2 — Fix: Registrazione Presidente dà "Not Found"

**Problema**: Dopo la registrazione, il presidente viene reindirizzato a `create_society`, ma questa route non esiste o non è configurata correttamente nelle URL.

**Fix**:
- Verificare la URL `create_society` in `core/urls.py`.
- Se mancante: creare la view e il template per la creazione della società.
- Il presidente deve poter creare la propria società durante il setup wizard.

**File da modificare**:
- `core/urls.py`, `core/views.py`, nuovo template `templates/societies/create_society.html`

---

## TASK 3 — Miglioramento Form: Registrazione Allenatore

**Cambiamenti richiesti**:
1. **Rimuovere** il campo `license_type` (tipo di licenza) dal form e dal template — non richiesto dall'utente.
2. **Specializzazione**: trasformare da campo libero a `<select>` con opzioni predefinite + opzione "Altro" con campo testo libero condizionale.
   - Opzioni: Portieri, Attacco, Difesa, Preparazione Atletica, Tattica, Settore Giovanile, Altro

**File da modificare**:
- `accounts/forms.py` — `CoachSetupForm`
- `accounts/models.py` — aggiungere campo `specialization_other` al `CoachProfile`
- `templates/accounts/setup_wizard.html` — logica JS per mostrare campo "altro" condizionale

---

## TASK 4 — Miglioramento Form: Registrazione Arbitro

**Cambiamenti richiesti**:
1. **Traduzione in italiano** delle label: "License Number" → "Numero Tessera", "License Level" → "Livello Arbitrale"
2. **Livello Arbitrale**: trasformare da campo libero a `<select>` con opzioni + "Altro":
   - Opzioni: Regionale, Interregionale, Nazionale, Internazionale, Altro

**File da modificare**:
- `accounts/forms.py` — `RefereeSetupForm` (label italiane, widget select)
- `accounts/models.py` — aggiungere campo `license_level_other` a `RefereeProfile`
- `templates/accounts/setup_wizard.html` — logica JS campo "altro"

---

## TASK 5 — Miglioramento Form: Registrazione Genitore/Fan

**Cambiamenti richiesti**:
1. **Scelta squadra**: Prima selezione campionato → poi squadra del campionato (dropdown a cascata via AJAX o select dinamico JS).
2. **Scelta giocatore**: Campo di ricerca per nome/cognome con risultati dinamici. L'utente vede i risultati e sceglie tra eventuali omonimi.

**Implementazione**:
- Aggiungere endpoint AJAX: `/api/teams-by-league/` per filtrare squadre per campionato.
- Aggiungere endpoint AJAX: `/api/search-athlete/` per cercare atleti per nome.
- Aggiornare `FanSetupForm` per gestire il flusso.
- Aggiornare `setup_wizard.html` con JS per dropdown a cascata e ricerca live.

**File da modificare**:
- `accounts/forms.py` — `FanSetupForm`
- `accounts/views.py` — nuovi endpoint AJAX
- `accounts/urls.py` — nuove URLs AJAX
- `templates/accounts/setup_wizard.html` — JS/UI per cascata e ricerca

---

## TASK 6 — Profilo Fan: Mostrare dati giocatore e squadra seguiti

**Cambiamenti richiesti**:
- Nel profilo del fan, mostrare:
  - **Dati del giocatore seguito**: stesse info della pagina profilo atleta (statistiche, squadra, ecc.)
  - **Per ogni squadra seguita**: classifica campionato + prossima partita

**File da modificare**:
- `accounts/views.py` — arricchire il context per `role == 'fan'`
- `templates/accounts/profile.html` — aggiungere sezioni fan

---

## TASK 7 — Mobile Responsiveness

**Problema**: Su mobile il sito è difficile da usare: elementi troppo grandi, layout non ottimizzato.

**Soluzione**:
- Ridurre padding/margin su mobile in `base.html` e template principali.
- Assicurare che tabelle classifiche siano scrollabili orizzontalmente.
- Compattare le card partite su schermi piccoli.
- Verificare font size e spacing su viewport mobile.
- Il menu mobile deve funzionare correttamente con tutte le voci di navigazione corrette.

**File da modificare**:
- `templates/base.html`
- `static/css/style.css`
- Template principali che mostrano tabelle (classifiche, partite)

---

## TASK 8 — Fix: Errore 500 Profilo Fan
**Problema**: Errore di sintassi nel template (`endif` mancante) e mancanza di controlli su dati nulli (league, next_match).
**Fix**: Ripristinata la corretta struttura dei tag Django nel template e aggiunti check di sicurezza.

---

## TASK 9 — Fix: Overlap Menu Mobile
**Problema**: Il menu mobile si sovrapponeva al contenuto (posizionamento `absolute`).
**Fix**: Cambiato posizionamento in `relative` per spingere il contenuto verso il basso durante l'apertura.

---

## TASK 10 — Fix: Salvataggio Preferenze Fan (Edit Profile)
**Problema**: La vista `edit_profile` non salvava i dati delle squadre/atleti preferiti.
**Fix**: Integrata la logica di salvataggio M2M anche nella vista di modifica.

---

## TASK 11 — UX: Pre-popolamento Form Fan
**Problema**: Modificando il profilo, i campi delle preferenze apparivano vuoti.
**Fix**: Aggiunto passaggio di dati `initial` nel form e logica JS per popolare i dropdown al caricamento della pagina.

---

## ORDINE DI ESECUZIONE (Ralph Loop)

1. ✅ Task 1 — Logout
2. ✅ Task 2 — Presidente
3. ✅ Task 3 — Form Allenatore
4. ✅ Task 4 — Form Arbitro
5. ✅ Task 5 — Form Fan
6. ✅ Task 6 — Profilo Fan
7. ✅ Task 7 — Mobile Responsiveness
8. ✅ Task 8 — Fix Profilo (500)
9. ✅ Task 9 — Fix Menu Mobile (Overlap)
10. ✅ Task 10 — Salvataggio Fan
11. ✅ Task 11 — Pre-popolamento Form

---
