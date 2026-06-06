## 16. Modello stagione e tesseramento per stagione

Stato: ⏳ Da fare

Redesign del modello stagione in 5 fasi: la **stagione diventa l'asse** del tesseramento (non più le date libere), la **lega** è la fonte di verità per la distinzione grandi/giovanili e si introduce il **prestito strutturato**. Le decisioni di prodotto sono **chiuse** (Sprint D, 2026-06-06, decision capture concluso); resta da implementare. Vedi [BLUEPRINT §10.1](../BLUEPRINT.md).

> **Nota di scope.** Le decisioni sono registrate come `- [x]`; i task implementativi come `- [ ]`. Nessun codice/migration/test è stato scritto in Sprint D. Il prestito porta uno stato come **semplice etichetta** (attivo/concluso): **non** è una macchina a stati, quindi [STATE_MACHINES.md](../STATE_MACHINES.md) non va toccato.

### 16.1 Bonifica dati (Fase 0)

Decisioni chiuse:

- [x] Formato canonico stagione: `2025/2026` (slash), validato sul pattern `AAAA/AAAA` con secondo anno = primo + 1.
- [x] Conversione valori esistenti: `2025-2026` → `2025/2026`; typo `2025-5026` → `2025/2026`.
- [x] Leghe/standings su `2024-2025` cancellati (residui di test, non dati reali).

Task implementativi:

- [ ] Management command idempotente di bonifica/normalizzazione dei valori `season` esistenti al formato slash.
- [ ] Cancellazione controllata dei residui `2024-2025` (leghe + standings collegate).
- [ ] Validator del formato `AAAA/AAAA` (secondo anno = primo + 1) riusabile da Season.

### 16.2 Entità Season (Fase 1)

Decisioni chiuse:

- [x] Nuova entità `Season` che sostituisce il CharField libero `League.season`.
- [x] Stagione corrente **per sport** (di norma allineate tra sport).
- [x] Flag `is_current` acceso a mano dall'admin; al massimo **una** stagione corrente per sport.
- [x] `Season` sostituisce il calcolo lessicografico `order_by('-season')` in [core/views.py:116](../../core/views.py#L116).
- [x] `Season` è distinta da `SeasonArchive` (Macro 13): asse del tesseramento vs archivio storico stats. Da linkare, non fondere.

Task implementativi:

- [ ] Modello `Season` (campi: identificativo formato `2025/2026` validato, `sport` FK, `is_current` bool) + migration.
- [ ] Constraint "al massimo una `is_current` per sport" (`UniqueConstraint` condizionale `condition=Q(is_current=True)` su `sport`).
- [ ] Migrare `League.season` (CharField) → FK a `Season`; backfill delle leghe esistenti.
- [ ] Sostituire il calcolo lessicografico in `core/views.py` con lookup `Season.is_current` per sport.
- [ ] **Backfill tesseramenti**: 58 Membership PLAYER (dev e prod allineate, verificato) → stagione `2025/2026`.

### 16.3 Membership per stagione (Fase 2)

Decisioni chiuse:

- [x] Campo `season` esplicito su `Membership` (FK a `Season`).
- [x] Nuova chiave di unicità: `(user, society, team, role, season)`.
- [x] Eliminazione di `start_date`/`end_date` da `Membership`.
- [x] Il `CheckConstraint` `membership_end_date_after_start` (migration `0009`, DEBT-003) decade col redesign.

Task implementativi:

- [ ] Aggiungere `Membership.season` (FK a `Season`) + migration.
- [ ] Sostituire `unique_together = (user, society, team, role)` con `(user, society, team, role, season)`.
- [ ] Rimuovere `start_date`/`end_date` e il `CheckConstraint` `membership_end_date_after_start` (migration `0009`) — vedi OPS_RUNBOOK §10.6 DEBT-003.
- [ ] Rivedere `MembershipQuerySet.active_at()` (oggi basato su date) → logica per stagione.
- [ ] Backfill `season = 2025/2026` sui 58 record PLAYER esistenti (dev + prod), poi migration che rende `season` NOT NULL.

### 16.4 Leghe grandi vs giovanili (Fase 3)

Decisioni chiuse:

- [x] La **lega** è la fonte di verità; si elimina la `category` duplicata/contraddittoria su `Team`.
- [x] Tipo lega da lista chiusa: `A1, A2, B, C, D` = "dei grandi"; `U10, U12, U14, U16, U18, U20` = giovanili.
- [x] Le giovanili hanno etichette tradizionali italiane come **display**, mappate 1:1 sul valore Under canonico: U12 = Esordienti, U14 = Ragazzi, U16 = Allievi, U18 = Juniores.

Task implementativi:

- [ ] Campo tipo lega su `League` da lista chiusa (TextChoices A1–D + U10–U20).
- [ ] Mapping display etichette tradizionali ↔ valore Under canonico.
- [ ] Rimuovere `Team.category` e migrare la lettura sulla lega.
- [ ] Helper "lega dei grandi?" per il gate del prestito (Fase 4).

### 16.5 Prestito strutturato (Fase 4)

Decisioni chiuse:

- [x] Unica eccezione a "una società per stagione".
- [x] Vale **solo** per squadre dei grandi (A1–D), mai giovanili.
- [x] Il giocatore in prestito mantiene tesseramento e giovanili nella società d'origine.
- [x] Constraint DB **rigido**: vietata una seconda società nella stessa stagione se la membership non è marcata prestito.
- [x] La membership di prestito porta: riferimento alla società di tesseramento + stato (attivo/concluso) come **etichetta semplice** (non macchina a stati → STATE_MACHINES.md non va toccato).

Task implementativi:

- [ ] Marcatore `is_loan` (o equivalente) + FK `tesseramento_society` su `Membership`.
- [ ] Campo stato prestito (attivo/concluso) come etichetta (CharField/choices, **non** state machine).
- [ ] Constraint DB: vietata 2ª società per `(user, season)` salvo membership marcata prestito su lega dei grandi.
- [ ] Validazione: prestito ammesso solo se la squadra di destinazione è "dei grandi".

### Note aperte

- [ ] **Trasferimento definitivo a stagione in corso**: come modellarlo senza violare il constraint prestito (cambio società "normale" entro la stessa stagione vs prestito). Da chiarire prima della Fase 4.
- [ ] **Censimento `order_by('-season')`**: trovare tutti i punti che ordinano lessicograficamente sul CharField `season` (almeno `core/views.py:116`) prima di rimuovere il campo.
- [ ] **Formato slash negli URL/slug**: `2025/2026` contiene `/`; valutare encoding o slug alternativo (`2025-2026`) per route e slug, mantenendo il display con slash.
- [ ] **Etichette U10/U20**: nessuna etichetta tradizionale assegnata — da decidere (display = valore Under canonico nel frattempo).
- [ ] **Constraint `membership_end_date_after_start` (migration 0009)**: da rimuovere in Fase 2 contestualmente all'eliminazione di `start_date`/`end_date` (DEBT-003, OPS_RUNBOOK §10.6).

---

← [Macro precedente](15_stabilita_tecnica.md)
