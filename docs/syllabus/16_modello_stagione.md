## 16. Modello stagione e tesseramento per stagione

Stato: ✅ **Implementata su dev** (giro Macro-intera batch, 2026-06-11). Propagazione a prod ancora da fare (giro master, §11.3 OPS_RUNBOOK).

Redesign del modello stagione in 5 fasi: la **stagione diventa l'asse** del tesseramento (non più le date libere), la **lega** è la fonte di verità per la distinzione grandi/giovanili e si introduce il **prestito strutturato**. Le decisioni di prodotto sono **chiuse** (Sprint D 2026-06-06 + D1–D4 del 2026-06-11); le Fasi 2/3/4 sono implementate su dev (suite 336 OK).
> **Nota di scope.** Le decisioni sono registrate come `- [x]`; i task implementativi come `- [x]` quando chiusi. Il prestito porta uno stato come **semplice etichetta** (attivo/concluso): non è una macchina a stati, quindi STATE_MACHINES.md non è stato toccato.

### 16.1 Bonifica dati (Fase 0)

Stato: ✅ **implementata** (dev + home, 2026-06-07). Propagazione a prod ancora da fare (giro master, §11.3).

Decisioni chiuse:

- [x] Formato canonico stagione: `2025/2026` (slash), validato sul pattern `AAAA/AAAA` con secondo anno = primo + 1.
- [x] Conversione valori esistenti: `2025-2026` → `2025/2026`; typo `2025-5026` → `2025/2026`. Conversione in **lockstep** `League.season` + `LeagueStanding.season` (stessa stagione) per non rompere `unique_together(league, team, season)`.
- [x] ~~Leghe/standings su `2024-2025` cancellati (residui di test).~~ **CORRETTO dai dati (Fase 0 audit/dry-run)**: si cancellano **solo** le leghe `2024-2025` realmente orfane (0 team **e** 0 standing collegati). Le leghe `2024-2025` che reggono team live + tesseramenti (es. lega "Senior" su dev: 4 team SENIOR + 58 PLAYER) **non** sono residui → sono leghe correnti mal-datate, **convertite** a `2025/2026` in lockstep con i loro standing (decisione C del product owner). La riclassificazione del tipo lega resta Fase 3.

Task implementativi:

- [x] Bonifica realizzata come **data migration tracciata** (non management command) per riproducibilità su prod: `core/migrations/0009_bonifica_season_slash.py` (`RunPython` idempotente, filtro per **pattern di valore** — mai pk hardcoded —, logging per record, pre-check collisioni `unique_together`, reverse irreversibile documentato → ripristino da backup).
- [x] Cancellazione controllata dei soli residui `2024-2025` orfani; conversione delle leghe mal-datate (lockstep League + standings).
- [x] Validator `core/validators.validate_season_format` (`AAAA/AAAA`, secondo anno = primo + 1) riusabile da Season; applicato a `League.season`, `LeagueStanding.season`, `SeasonArchive.season` (migration `core/0010`, `seasons/0002`).
- [x] `League.save()` sanitizza il separatore nello slug (`/`→`-`) così i nuovi record con season slash non producono `/` nello slug. Gli slug esistenti **non** sono stati rigenerati (scelta: evitare churn pre-lancio).

### 16.2 Entità Season (Fase 1)

Decisioni chiuse:

- [x] Nuova entità `Season` che sostituisce il CharField libero `League.season`.
- [x] Stagione corrente **per sport** (di norma allineate tra sport).
- [x] Flag `is_current` acceso a mano dall'admin; al massimo **una** stagione corrente per sport.
- [x] `Season` sostituisce il calcolo lessicografico `order_by('-season')` in [core/views.py:116](../../core/views.py#L116).
- [x] `Season` è distinta da `SeasonArchive` (Macro 13): asse del tesseramento vs archivio storico stats. Da linkare, non fondere.

Task implementativi:

- [x] Modello `Season` (campi: identificativo formato `2025/2026` validato, `sport` FK, `is_current` bool) + migration.
- [x] Constraint "al massimo una `is_current` per sport" (`UniqueConstraint` condizionale `condition=Q(is_current=True)` su `sport`).
- [x] Migrare `League.season` (CharField) → FK a `Season`; backfill delle leghe esistenti.
- [x] Sostituire il calcolo lessicografico in `core/views.py` con lookup `Season.is_current` per sport.
- [x] **Backfill tesseramenti**: 58 Membership PLAYER (dev e prod allineate, verificato) → stagione `2025/2026`.

### 16.3 Membership per stagione (Fase 2)

Decisioni chiuse:

- [x] Campo `season` esplicito su `Membership` (FK a `Season`).
- [x] Nuova chiave di unicità: `(user, society, team, role, season)`.
- [x] Eliminazione di `start_date`/`end_date` da `Membership`.
- [x] Il `CheckConstraint` `membership_end_date_after_start` (migration `0009`, DEBT-003) decade col redesign.
- [x] Attribuzione partite-allenatore: modello **β-stagione, coach finale**. Il coach "della stagione" per una squadra è quello in carica a fine stagione; a lui sono attribuite **tutte** le partite della squadra in quella stagione. Nessuna finestra temporale (`start_date`/`end_date`) nel calcolo dell'attribuzione.
- [x] Cambio coach in corso di stagione (chi→chi, quando): registrato come **nota descrittiva** (testo libero), **non** come dato strutturato che piloti l'attribuzione. Campo da aggiungere/verificare nella fetta 2d. ✅ implementato 2d-2 (`Membership.coach_change_note`, migration `0012`, commit `7f3cb63`).
- [x] Sostituzione spot per singole partite: **non modellata**.
- [x] Timeline cambi-coach strutturata/interrogabile: feature futura separata, **fuori Fase 2**.

Task implementativi:

- [x] Aggiungere `Membership.season` (FK a `Season`) + migration.
- [x] Sostituire `unique_together = (user, society, team, role)` con `(user, society, team, role, season)`. ✅ implementato 2d-4a (`UniqueConstraint` 5-field, migration `0013`, commit `3696cd3`).
- [x] Rimuovere `start_date`/`end_date` e il `CheckConstraint` `membership_end_date_after_start` (migration `0009`) — vedi OPS_RUNBOOK §10.6 DEBT-003. ✅ implementato 2d-6 (migration `0014_remove_membership_dates`; DEBT-003 ritirato; rimosso anche il management command `backfill_membership_dates`, obsoleto).
- [x] Rivedere `MembershipQuerySet.active_at()` (oggi basato su date) → logica per stagione. ✅ implementato 2d-6: `active_at(date)` sostituito da `active()` (is_active) e `active_in_season(season)` — non esiste più la nozione "attiva a una data".
- [x] Backfill `season` sui 58 record esistenti (migration `0011`, dev reale 58/58 → `2025/2026`).
- [x] Migration `season` NOT NULL — ✅ implementato 2d-7 (migration `0015_membership_season_notnull`): RunPython consolida i NULL residui con la derivazione del backfill ed è **fail-fast** (solleva con elenco pk se non derivabili; migration atomica, il flip non passa). I 3 creation-site falliscono ora in modo esplicito se la stagione non è derivabile (messaggio utente su redeem/approve, RuntimeError sul signal) invece di produrre righe NULL. Test dedicato `management/tests_migrations_membership_notnull.py`.

> **Nota tecnica — logica date in produzione da ridisegnare in Fase 2.** Oggi due punti del codice dipendono dalle date di `Membership` e non erano mappati in questa sezione:
> - `management/signals.py` — lifecycle "attiva" = `end_date IS NULL` (apertura/chiusura automatica delle Membership sui save dei profili). Da riportare su `season` nella fetta 2d (rimozione date). ✅ predicato disaccoppiato dalle date via `is_active` in 2d-5 (commit `dd70cb3`); ✅ rimozione `start_date`/`end_date` completata in 2d-6 (migration `0014`): la chiusura è il solo flip `is_active=False`, riga storica conservata.
> - `accounts/views.py` (§10.4) — tenure coach per **finestra-data** (`match_date` tra `start_date` e `end_date` della Membership HEAD_COACH) per attribuire le partite dirette. Da sostituire con il modello β-stagione/coach-finale nella fetta 2d. ✅ sostituito col modello β-stagione/coach-finale in 2d-3 (attribuzione via `league.season_fk`, commit `b2bc2cc`).

> **Blocker 2c (NOT NULL) → rinviato a fine 2d.** Il flip `season` NOT NULL non è schema-only: lo storico è popolato (58/58) ma 3 creation-site di produzione creano `Membership` senza `season` — `management/signals.py:66` (`_open_or_reopen_membership`), `management/views.py:417` (approvazione MembershipRequest), `management/services/membership_enrollment.py:69` (redeem activation code). Con FK nullable nascono `season=NULL`; con NOT NULL romperebbero in runtime. I 3 siti vanno resi season-aware in 2d (derivazione come il backfill: `team.league.season_fk` → fallback `is_current`), contestualmente alla nuova unique key che li tocca comunque. Il NOT NULL è quindi l'ultimo gradino di 2d. ✅ i 3 siti resi season-aware: 2d-1 (`defaults` season-aware, commit `35fda4f`) + 2d-4b (lookup season-aware + guard `season=None`, commit `8e99a5e`); ✅ flip NOT NULL eseguito in 2d-7 (migration `0015`) — la guard `season=None` è diventata fail-fast esplicito nei 3 siti.

### 16.4 Leghe grandi vs giovanili (Fase 3)

Decisioni chiuse:

- [x] La **lega** è la fonte di verità; si elimina la `category` duplicata/contraddittoria su `Team`.
- [x] Tipo lega da lista chiusa: `A1, A2, B, C, D` = "dei grandi"; `U10, U12, U14, U16, U18, U20` = giovanili.
- [x] Le giovanili hanno etichette tradizionali italiane come **display**, mappate 1:1 sul valore Under canonico: U12 = Esordienti, U14 = Ragazzi, U16 = Allievi, U18 = Juniores.

Task implementativi:

- [x] Campo tipo lega su `League` da lista chiusa (TextChoices A1–D + U10–U20). ✅ `League.league_type` nullable (NULL = non classificata, "Null invece di invenzione"), migration `core/0015`; classificazione per **pattern di nome** (mai pk) in `core/0016` (nomi non riconosciuti → NULL + warning). Rimosso anche il campo duplicato `League.category` (migration `core/0018`).
- [x] Mapping display etichette tradizionali ↔ valore Under canonico. ✅ `League.LEAGUE_TYPE_DISPLAY` (dizionario in codice, decisione D1 2026-06-11: U10=Pulcini, U12=Esordienti, U14=Ragazzi, U16=Allievi, U18=Juniores, U20=Under 20; grandi = "Serie <tipo>") + property `league_type_label`.
- [x] Rimuovere `Team.category` e migrare la lettura sulla lega. ✅ migration `core/0018`: via category/CATEGORY_CHOICES/unique_together(society,category); display via `Team.category_label` (deriva da `league.league_type_label`); name/slug auto-generati dal tipo lega; `society_setup` non crea più la ladder di 7 squadre per categoria ma la sola prima squadra.
- [x] Helper "lega dei grandi?" per il gate del prestito (Fase 4). ✅ property `League.is_senior_league` (league_type in A1–D; NULL → False).
- [x] **Rifusione scaffolding (decisione D4-A, 2026-06-11):** la lega-ombrello "Senior" (non mappabile sulla lista chiusa: NON è un tier reale) è stata rifusa in place in "serie C Maschile" tipo `C` via data migration `core/0017` (selezione per nome, pk conservato: team/standing/58 Membership agganciati; slug rigenerato in deroga documentata — dati finti pre-lancio). Set d'esempio risultante: B (2 gironi) + C dei grandi, U16 + U18 giovanili.

### 16.5 Prestito strutturato (Fase 4)

Decisioni chiuse:

- [x] Unica eccezione a "una società per stagione".
- [x] Vale **solo** per squadre dei grandi (A1–D), mai giovanili.
- [x] Il giocatore in prestito mantiene tesseramento e giovanili nella società d'origine.
- [x] Constraint DB **rigido**: vietata una seconda società nella stessa stagione se la membership non è marcata prestito.
- [x] La membership di prestito porta: riferimento alla società di tesseramento + stato (attivo/concluso) come **etichetta semplice** (non macchina a stati → STATE_MACHINES.md non va toccato).

Task implementativi:

- [x] Marcatore `is_loan` (o equivalente) + FK `tesseramento_society` su `Membership`. ✅ migration `management/0016` (FK PROTECT alla società d'origine, related_name `loaned_out_memberships`).
- [x] Campo stato prestito (attivo/concluso) come etichetta (CharField/choices, **non** state machine). ✅ `Membership.LoanStatus` (ACTIVE/ENDED), default vuoto per non-prestiti; STATE_MACHINES.md invariato.
- [x] Constraint DB: vietata 2ª società per `(user, season)` salvo membership marcata prestito su lega dei grandi. ✅ realizzato su due livelli: a livello **DB** il `CheckConstraint` `membership_loan_fields_coherent` (coerenza campi prestito); il vincolo **cross-row** "una sola società ATTIVA per (user, season) salvo prestito" non è esprimibile come constraint Django (richiede di vedere le altre righe) e vive in `Membership.clean()` — conta solo le membership **attive** non-prestito (decisione D2: il trasferimento definitivo in-season è una **successione**, la riga chiusa resta come storico e non blocca).
- [x] Validazione: prestito ammesso solo se la squadra di destinazione è "dei grandi". ✅ in `clean()` via `league.is_senior_league` (giovanili e leghe non classificate rifiutate); più: società d'origine obbligatoria e diversa dalla destinazione, normalizzazione stato → Attivo. Test: `management/tests_membership_loan.py`.

### Note aperte

- [x] **Trasferimento definitivo a stagione in corso** — chiuso (decisione D2, 2026-06-11): è una **successione**. Si chiude la membership d'origine (`is_active=False`, riga storica conservata) e si apre la nuova; il prestito resta l'**unico** caso di due membership attive contemporanee nella stessa stagione. Il vincolo di Fase 4 conta quindi solo le membership **attive** non-prestito, non è assoluto sulle righe chiuse.
- [ ] **Regola di dominio "convocazione-lock" (registrata 2026-06-11, FUORI SCOPE Macro 16 — solo documentale).** Un giocatore convocato/sceso in campo in almeno una partita con la squadra X in un gruppo-categoria non può giocare quella stagione con la squadra Y nello **stesso gruppo-categoria**. Granularità: le giovanili sono per singolo Under (U18 con U18, ecc.); **tutte** le senior (A1, A2, B, C, D) collassano in **un unico gruppo** ("se hai giocato in B non puoi passare in A2 quella stagione"). Trigger = aver giocato/essere stato convocato ad almeno una partita, **non** il semplice tesseramento: è un check a livello **convocazione/roster**, NON un constraint sulla Membership (il DB non vede "aver giocato"). Verificato 2026-06-11: il layer convocazioni (`Convocation`/`ConvocationNominee`) non è toccato da Macro 16, quindi la regola resta puramente documentale; la Fase 4 implementata (successione + vincolo sulle sole attive) non la contraddice. Da implementare quando si lavorerà sul flusso convocazioni.
- [x] **Censimento `order_by('-season')`** — chiuso. `core/views.py:117` (League, punto core) risolto in Fase 1 (commit `bd0dbfc`, lookup `Season.is_current`). I due punti su `SeasonArchive` — `seasons/models.py:30` (`Meta.ordering=['-season']`) e `accounts/views.py:511` (`SeasonArchive.objects.order_by('-season')`) — sono già coperti: il campo `SeasonArchive.season` porta `validators=[validate_season_format]` dalla Fase 0 (commit `1816567`, migration `seasons/0002`), che vincola il formato al canonico `2025/2026`, rendendo l'ordinamento lessicografico corretto a regime. Limite noto: il validator scatta su `full_clean()`, non su `.save()` nudo — irrilevante oggi (`SeasonArchive` ha 0 righe e 0 scrittori), da ricordare se la tabella verrà popolata in Fase 2.
- [ ] **Formato slash negli URL/slug**: `2025/2026` contiene `/`; valutare encoding o slug alternativo (`2025-2026`) per route e slug, mantenendo il display con slash. **Confermato fuori scope anche nel giro 2026-06-11 (decisione D3)**: `League.save()` già sanitizza `/`→`-` negli slug nuovi, la nota resta aperta.
- [x] **Etichette U10/U20** — chiuso (decisione D1, 2026-06-11): U10 = "Pulcini", U20 = "Under 20". Mapping completo in `League.LEAGUE_TYPE_DISPLAY` (dizionario in codice, modificabile senza migration).
- [x] **Constraint `membership_end_date_after_start` (migration `management/0009`)** — chiuso: rimosso in Fase 2 (migration `management/0014`) insieme a `start_date`/`end_date`. DEBT-003 ritirato (OPS_RUNBOOK §10.6 annotato).
- [ ] **Incoerenza slug girone (preesistente)**: su dev gli slug delle leghe "serie B Maschile" sono disallineati al `group_name` reale — lega con `group_name='Girone C'` ha slug `...-girone-d`, e una con `group_name='Girone D'` ha slug `...-girone-D` (maiuscola non slugificata). Indipendente dalla stagione, **non** sanitizzato in Fase 0 (gli slug esistenti non si rigenerano): da indagare in futuro.

---

← [Macro precedente](15_stabilita_tecnica.md)
