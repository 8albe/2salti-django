## 12. Live Alerts e notifiche push

Stato: 🧊 Differito (fonti trigger pronte; manca solo il push: gating Premium dipende dalla Macro 10 non pronta + infrastruttura push da provisionare)

Notifiche push per risultati live, variazioni orario, convocazioni. Gated Premium.

### 12.1 Infrastruttura

- [ ] Service worker e registrazione device
- [ ] Channel per match
- [ ] Gating Premium server-side

### 12.2 Trigger

- [ ] Trigger su transizioni `MatchReport` (gol live, fine periodo, fine partita)
- [ ] Trigger su variazioni convocazione (`Convocation`)
- [ ] Trigger su variazioni orario partita

### 12.3 Preferenze utente

- [ ] Preferenze per categoria alert (solo squadra propria, solo match con figlio, ecc.) — collegato a User Preferences

### 12.4 Fonti di trigger già implementate (manca solo il push)

- [x] **Convocations** — modello `Convocation` + `ConvocationNominee`, 4 stati (3 DB + 1 calcolato LOCKED), property `current_effective_status` (STATE_MACHINES.md §6)
- [ ] Push su variazione/lock convocazione
- [x] **Training Attendance** — modelli `Training`, `TrainingOccurrence`, `TrainingAttendance` con ricorrenze JSON e geofencing (lat/lng/accuracy)
- [ ] Push su check-in/assenza training
- [x] **Team Communications** — modelli `Post`, `Comment`, `ChatMessage` per bacheca + chat informale
- [ ] Push su nuovo post bacheca (gated Club Pro scrittura, lettura tutti)
- [ ] Test coverage per Convocations, Training, Team Communications (oggi senza test dedicati — vedi macro 15)

---

← [Macro precedente](10_subscription_piani.md) | → [Macro successiva](13_season_archive.md)
