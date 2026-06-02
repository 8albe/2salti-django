# 2salti — Blueprint di Prodotto

> Versione 1.0 — 2026-05-20
> Documento di visione e architettura. Non contiene roadmap operative.

## 1. Visione e principi

**2salti è la piattaforma multi-sport che trasforma ogni referto ufficiale in un archivio sportivo vivo.** Partite, classifiche, profili atleti, statistiche arbitrali e leaderboard nascono dallo stesso motore dati, alimentato da referti compilati nativamente in-app oppure estratti via OCR da copie cartacee.

### Il problema che risolve

Il dato sportivo amatoriale e semi-professionale oggi è frammentato: referti cartacei che vivono in foto WhatsApp, statistiche calcolate a mano in fogli Excel, profili atleta inesistenti, classifiche compilate manualmente dai dirigenti. 2salti centralizza ingestione, validazione e pubblicazione, eliminando la duplicazione di lavoro e dando per la prima volta un'identità digitale verificabile a chi pratica lo sport.

### Principi non negoziabili

- **Null invece di invenzione.** Se un dato non è leggibile o non è certo, il sistema lo segnala come mancante. Non si indovina mai.
- **Ogni numero tracciabile alla fonte.** Ogni statistica aggregata deve poter essere ricostruita dai `MatchEvent` pubblicati, fino al referto sorgente.
- **Pagine pubbliche e admin alimentate dallo stesso backend.** Niente duplicazione di logiche o contenuti.
- **Affidabilità prima della profondità.** Prima usabilità interna, poi profondità pubblica, poi mobile e integrazioni.
- **Esperienza guest e autenticata chiaramente diverse.** Da pubblico si scopre, da autenticato si agisce.
- **Le correzioni umane lasciano sempre audit log** con utente, timestamp, diff e motivazione.

### Multi-sport by design

La pallanuoto è il primo sport di rollout — non il perimetro del prodotto. Architettura, naming, navigazione, point system, period label e dominio degli eventi sono pensati come framework estendibile. `Sport` è un'entità di prima classe; le partite hanno `point_system` e `period_label` configurabili; l'enum eventi è canonicizzato a 5 valori comuni (`GOAL`, `EXCLUSION_20`, `YELLOW_CARD`, `RED_CARD`, `TIMEOUT`) più `OTHER` per estensioni future.

## 2. Ecosistema utenti

### Ruoli e valore generato

| Ruolo | Valore Freemium | Valore aggiunto Premium / Club Pro |
|---|---|---|
| Atleta | Profilo sportivo, gol, presenze, crescita | Media Gallery, Season Recap, dashboard personalizzata |
| Genitore / Tifoso | Consultazione bacheca e statistiche | Live Alerts push, Chatbot AI, widget personalizzati |
| Allenatore | Rendimento squadra, record | Statistiche avanzate, gestione bacheca via Club Pro |
| Arbitro / Giuria | Consultazione cronologia | Referto Digitale mobile, firma ufficiale, certificazione |
| Società / Lega | Pagina base, roster, calendario | Bacheca push, Shop vetrina, Sponsor, Widget Club |
| Admin | Cockpit unico di governo | Monitoraggio pipeline, audit log, gestione permessi |

### Guest vs autenticato

L'area pubblica e l'area autenticata sono esperienze nettamente diverse. Da guest si scoprono dati generali: classifiche, risultati, schede squadra e profili pubblici. Da autenticato si entra in dashboard personali (preferenze utente, widget), strumenti operativi (claim profilo, membership, convocazioni) e funzioni di ruolo (review admin, compilazione Referto Digitale per la giuria).

### I tre piani

| Piano | Pubblico target | Cosa sblocca |
|---|---|---|
| **Freemium** | Utente base | Pagine pubbliche, claim profilo, lettura bacheca della propria società |
| **Premium Utente** | Famiglie, atleti, tifosi | Chatbot AI, Live Alerts push, upload Media Gallery, Season Recap, dashboard widget personalizzata |
| **Club Pro** | Società e club | Scrittura bacheca + push agli iscritti, Shop vetrina, gestione Sponsor, Pagina Club personalizzata |

La giuria certificata usa il Referto Digitale gratuitamente, sempre, tramite token match-specific emesso dalla federazione/lega.

## 3. Struttura del prodotto

### Aree pubbliche

| Pagina | Scopo |
|---|---|
| Home / Landing Sport | Hub di ingresso con campionati, classifiche teaser, sport navigator |
| Partite / Match Detail | Calendario filtrabile, risultati, tabellini, cronologia eventi |
| Classifiche / Statistiche | Standing squadre + leaderboard marcatori |
| Scheda squadra / Società | Roster, staff, sponsor, bacheca pubblica, eventuale redirect a sito esterno del club |
| Profili Atleta / Coach / Arbitro | Identità sportiva, storico, metriche stagione |

### Aree autenticate

| Pagina | Scopo |
|---|---|
| Dashboard personalizzata | Widget riordinabili (Premium), alert, preferenze |
| Bacheca squadra | Comunicazioni gated: scrittura Club Pro, lettura tutti gli iscritti |
| Media Gallery partita | Upload (Premium) e visualizzazione foto/video taggati |
| Vetrina Shop Società | Catalogo prodotti con pulsante "Richiesta Materiale" |
| Chatbot Panel | Interfaccia AI per query e comandi operativi |
| Form Referto Digitale | Compilazione mobile per la giuria, firma PIN, sync offline |
| Admin Cockpit | Review OCR, validazione, audit log, publishing |

### Principio di separazione

Le pagine pubbliche massimizzano scoperta e trasparenza del dato. Le pagine autenticate massimizzano azione, personalizzazione e funzioni di ruolo. Niente sovrapposizione: nessuna scrittura sul pubblico, nessuna gerarchia di scoperta sul privato.

## 4. Acquisizione del dato sportivo

### I tre canali di ingresso

1. **Referto Digitale in-app** (primario). La giuria compila direttamente da smartphone un referto strutturato, firma con PIN arbitro a fine gara, sync offline-first. Output JSON identico al canale OCR.
2. **OCR su cartaceo** (fallback). Email/WhatsApp ingestion automatica più upload admin manuale; pipeline LLM Vision con quality gate, confidence per campo, raw evidence salvata.
3. **Upload manuale admin** (emergenza). Solo per casi eccezionali, sempre con tracciamento.

### Workflow del referto

Il `MatchReport` attraversa 8 stati, in due flussi iniziali che convergono su `VALIDATED → PUBLISHED`:

```
FILE:    UPLOADED → PROCESSING → EXTRACTED → VALIDATED → PUBLISHED
DIGITAL: DRAFT → VALIDATED → PUBLISHED
Branch:  PROCESSING → NEEDS_REVIEW (quality gate / errore OCR)
         qualsiasi stato → REJECTED (motivazione obbligatoria)
         REJECTED / NEEDS_REVIEW → PROCESSING (riprocessamento)
```

Solo lo stato `PUBLISHED` aggiorna match, standings e statistiche atleti. Ogni transizione produce un `MatchReportAuditLog` con utente, timestamp, diff e motivazione. La fonte di verità autoritativa con transizioni e side effects è [STATE_MACHINES.md §1](STATE_MACHINES.md).

### Convergenza

OCR e Referto Digitale producono lo stesso contratto dati JSON (`schema_version: 2.0`, definito in [matches/services/schema.py](../matches/services/schema.py)) e attraversano lo stesso workflow di validazione. Un match con referto digitale nativo non rifà OCR; un match con solo cartaceo passa per OCR e poi per review umana.

### Guardrails di pubblicazione

- **Quality gate.** `OCRSchemaValidator.assess_publish_readiness` produce blocker e warning. Se `safe=False` la publish è bloccata.
- **Riconciliazione incompleta = blocker.** Eventi con riferimenti a giocatori non riconciliati bloccano la publish per evitare drift nelle statistiche atleti.
- **Force override.** `publish_report(force=True)` bypassa i blocker ma li logga in `AuditLog.details.overridden_blockers`.
- **Concurrent publish guard.** `select_for_update()` sul report dentro transazione + doppio check dello stato dopo lock.
- **Zero events strict.** Un report con `score>0` e zero eventi creati abortisce la transazione anche con `force=True`.

## 5. Architettura tecnica

### Stack

- **Backend:** Django 5.0, Python 3.11+
- **DB:** SQLite in dev e in prod (migrazione PostgreSQL pianificata pre-scala)
- **Web:** Gunicorn (socket unix `/tmp/2salti.sock`) + Nginx (TLS, reverse proxy). Static files serviti da Whitenoise (app) con nginx alias `/static/` davanti.
- **Frontend:** template Django + Tailwind via `django-crispy-forms` + `crispy-tailwind`
- **OCR:** provider astratto, GPT-4V (OpenAI) in produzione, `MockVisionProvider` nei test
- **Hosting:** singola VPS Hetzner che serve `2salti.com` e `dev.2salti.com`

### Le 6 app Django

| App | Responsabilità |
|---|---|
| `accounts` | Custom User model, onboarding state machine, profili di ruolo, claim profilo |
| `core` | Sport, Society, Team, League, LeagueStanding, viste pubbliche |
| `matches` | Match, MatchEvent, MatchReport, OCR pipeline, publishing, AI Stats Engine v0 |
| `management` | Membership, training, convocations, audit logging, comunicazioni, pilot tooling |
| `seasons` | Archivio storico statistiche per stagione |
| `config` | Settings, root URL conf, WSGI |

### Modelli strutturali

| Modello | App | Funzione |
|---|---|---|
| `User` | accounts | AbstractUser con `role`, `staff_role`, `identity_status`, `subscription_status` |
| `AthleteProfile` / `CoachProfile` / `RefereeProfile` / `PresidentProfile` | accounts | Profili sportivi 1:1 con User, creati via signal post_save |
| `AccountProfileLink` | accounts | Claim profilo sportivo preesistente |
| `Sport` | core | Sport con `point_system` e `period_label` configurabili |
| `Society` | core | Società sportiva, contiene `sponsors` JSON |
| `Team` | core | Squadra di una società in un campionato |
| `League` | core | Campionato con stagione, girone, livello |
| `LeagueStanding` | core | Classifica denormalizzata — solo via `standings_service` |
| `Match` | matches | Partita con score, quarter_scores, referees |
| `MatchEvent` | matches | Riga per ogni evento (gol, espulsione, cartellino, timeout) |
| `MatchReport` | matches | Referto cartaceo o digitale, `source_channel` discrimina |
| `MatchReportAuditLog` | matches | Audit dedicato al workflow referto |
| `Membership` / `MembershipRequest` / `ActivationCode` | management | Appartenenza utente a società/squadra |
| `Convocation` / `ConvocationNominee` | management | Convocazione ufficiale atleti per partita |
| `Training` / `TrainingOccurrence` / `TrainingAttendance` | management | Pianificazione allenamenti con geofencing |
| `AuditLog` | management | Log generico di sistema |

### Le 9 state machines

| # | Modello | Campo / Property | Stati |
|---|---|---|---|
| 1 | `MatchReport` | `status` (campo DB) | DRAFT, UPLOADED, PROCESSING, EXTRACTED, VALIDATED, PUBLISHED, NEEDS_REVIEW, REJECTED |
| 2 | `User` onboarding | `onboarding_state` (property calcolata) | IDENTITY_PENDING, PAYMENT_PENDING, SETUP_PENDING, MEMBERSHIP_PENDING, COMPLETED |
| 3 | `User.staff_role` | campo DB | NONE, UPLOADER, REVIEWER, PUBLISHER, SUPERADMIN |
| 4 | `AccountProfileLink` | `status` | PENDING, APPROVED, REJECTED |
| 5 | `MembershipRequest` | `status` | PENDING, APPROVED, REJECTED |
| 6 | `Convocation` | `status` + property `current_effective_status` | DRAFT, SENT_PRIVATE, PUBLISHED, LOCKED (calcolato) |
| 7 | `TrainingAttendance` | `status` | PENDING, PRESENT, ABSENT, JUSTIFIED |
| 8 | `PilotBug` | `status` | NEW, TRIAGED, IN_PROGRESS, MITIGATED, CLOSED, VERIFIED |
| 9 | `PilotFeedback` | `status` | NEW, ACKNOWLEDGED, PLANNED, DONE, WONT_FIX |

Fonte di verità completa con transizioni e side effects: [STATE_MACHINES.md](STATE_MACHINES.md).

### Regole non negoziabili del codice

- Mai chiamare OpenAI nei test — `OCR_PROVIDER=mock` o patch di `vision_providers.py`.
- Mai modificare migrazioni già committate — sempre nuova migration via `makemigrations`.
- Mai usare `User` direttamente — sempre `get_user_model()`.
- Mai scrivere su `LeagueStanding` — sempre `standings_service.rebuild_league_standings()`.
- Sempre `Europe/Rome` timezone-aware — mai datetime naive.
- Nessun commit senza `python manage.py check` e i test dell'app toccata.
- Nessun commit di segreti o `.env*`, `*.service`, `*.timer`, `psw.*`, `*_history`.

### Ambienti

| Ambiente | Path | Dominio | Note |
|---|---|---|---|
| Dev locale | `/home/alberto/` | — | Repo di sviluppo dello sviluppatore |
| Prod | `/opt/2salti-new/` | `2salti.com` | Service `2salti.service`, pull manuale post-commit |
| Dev remoto | `/opt/2salti-dev/` | `dev.2salti.com` | Auto-pull ogni 2 min da branch `dev` |

Le tre copie del repo coesistono sulla stessa VPS Hetzner. Pull non automatico fra `/home/alberto/` e `/opt/2salti-new/` — disciplina manuale documentata in [OPS_RUNBOOK.md §2](OPS_RUNBOOK.md).

## 6. Modello di business

### Three-tier

| Piano | Prezzo guida | Target | Feature chiave |
|---|---|---|---|
| **Freemium** | Gratis | Utente base | Pagine pubbliche, claim profilo, lettura bacheca |
| **Premium Utente** | TBD mensile | Famiglie, atleti, tifosi | Chatbot AI, Live Alerts, Media Gallery upload, Season Recap, dashboard custom |
| **Club Pro** | TBD mensile | Società / Club | Scrittura bacheca + push iscritti, Shop vetrina, Sponsor, pagina Club personalizzata |

### Chi paga cosa, chi riceve cosa

- **Premium Utente** paga per servizi avanzati personali (Alerts, Chatbot, Gallery, Recap, personalizzazione).
- **Club Pro** paga la società per visibilità (Sponsor, pagina), gestione operativa (Shop) e comunicazione diretta (Bacheca push).
- **Giuria certificata** usa il Referto Digitale sempre gratis tramite token match-specific.
- **Lettura bacheca e dati base** restano gratis per tutti gli iscritti alla società (Freemium inclusi). Le push sulla bacheca vanno solo ai Premium.

### Funnel di attivazione

1. Registrazione account base (email/password o OAuth).
2. Verifica identità (SPID/CIE primario; fallback documento + selfie per casi eccezionali).
3. Selezione piano (Freemium subito attivo; Premium o Club Pro richiedono pagamento).
4. Claim del profilo sportivo (ricerca + richiesta di possesso).
5. Accesso squadra tramite codice di attivazione del club o richiesta manuale al Club Admin.
6. Approvazione finale, sblocco delle aree private.

L'accesso a dati privati richiede SEMPRE entrambe le condizioni: **identità verificata + membership sportiva approvata**.

### Punti aperti da validare con il product owner

- **Federazione token giuria.** Chi è l'autorità che emette i token? Nazionale, lega o club?
- **Conflict resolution sync.** Policy se due dispositivi giuria editano lo stesso match contemporaneamente.
- **Shop SLA.** Quante ore di retry sul webhook verso società? Notifica admin club in caso di failure?
- **UX sito esterno club.** Redirect diretto (A) vs pagina teaser con badge (B)?
- **Gallery moderazione.** Segnalazione automatica o dashboard manuale Club Admin?
- **Chatbot function calling.** Aperto (A) vs whitelist chiusa di comandi (B)?
- **Privacy Recap minorenni.** Opt-in solo per condivisione o anche per generazione PDF?
- **Identity fallback.** Chi valida manualmente i documenti nel fallback SPID? Staff 2salti o Club Admin?

## 7. Decisioni bloccate

Decisioni architetturali già prese, non più in discussione (baseline v3 del blueprint).

- **Referto Digitale = via principale di ingestione.** L'OCR resta come fallback per cartaceo e archivio storico, ma il futuro del dato è la compilazione nativa in-app. Più veloce, meno error-prone, più tracciabile.
- **Three-tier pricing.** Freemium / Premium Utente / Club Pro. Niente piani-mosaico, niente add-on à la carte. Prezzi puntuali TBD.
- **Widget Layout a slot fissi riordinabili.** Niente drag&drop libero stile Canva. Personalizzazione = ordinare e nascondere widget pre-definiti.
- **Chatbot AI esclusiva Premium**, con function calling e RBAC server-side obbligatorio. Niente bypass via prompt.
- **Bacheca mista.** Scrittura gated Club Pro, lettura gratis per tutti gli iscritti, notifiche push solo Premium.
- **Shop = intermediario, non venditore.** Webhook outbound firmato HMAC o email strutturata verso lo shop della società. Nessun checkout in-app, niente custodia ordini.
- **Certificazione giuria via token match-specific.** Finestra 30 minuti pre-match, revoca automatica al fischio finale, revoca manuale admin disponibile.
- **Firma PIN arbitro = immutabilità.** Il referto firmato non si modifica più: correzioni successive solo via admin con audit log completo.
- **AI tagging media + coda review manuale.** Detection automatica ma validazione umana prima della pubblicazione. Opt-in esplicito per minorenni, opt-out disponibile per ogni atleta.
- **Profili sportivi pre-caricati = il sistema, non l'utente.** Gli utenti rivendicano profili esistenti, non li creano da zero. Garantisce coerenza anagrafica e prevenzione duplicati.
- **Verifica identità SPID/CIE primaria.** Fallback documento + selfie per stranieri, minorenni e casi eccezionali.
- **Doppia condizione per dati privati.** Identità verificata + membership sportiva approvata. Una sola delle due non basta mai.
- **Multi-sport by design.** Pallanuoto è il primo rollout, non il limite. Naming, navigazione, design system e dominio devono restare estendibili ad altri sport.

## 8. Funzionalità non ancora implementate

Feature descritte nel blueprint ma assenti nel codice. Fonte: [FEATURE_STATUS.md](FEATURE_STATUS.md) §"Feature non ancora implementate".

| # | Feature | Riferimento blueprint | Stato |
|---|---|---|---|
| 1 | Jury Tokens (token match-specific) | §7.4, §10, §14 | Roadmap futura |
| 2 | Firma arbitro / PIN referto immutabile | §7.4.3, §14 | Roadmap futura |
| 3 | Ruolo "Giuria" nell'enum `User.role` | §7.1 | Decisione pendente (aggiungere valore o gestire come sotto-ruolo di referee) |
| 4 | Media Gallery + AI Tagging | §7.6 | Roadmap futura |
| 5 | Live Alerts push | §2, §13 | Roadmap futura |
| 6 | Shop vetrina + webhook HMAC | §2, §3, §13 | Roadmap futura |
| 7 | User Preferences / Widget Dashboard personalizzata | §7.1, §12 | Roadmap futura |
| 8 | Subscription three-tier (Freemium / Premium / Club Pro) | §13 | Decisione pendente (pricing) + roadmap implementativa |
| 9 | Season Recap PDF | §7.1, §13 | Modello `SeasonArchive` esiste, generazione PDF no |
| 10 | SPID/CIE identity verification automatica | §7.3 | Campo `identity_status` esiste, integrazione no |

Nessuna delle 10 è considerata bug: tutte appartengono alla roadmap esplicita del prodotto. La priorità di esecuzione è definita in [SYLLABUS.md MACRO 3](SYLLABUS.md).

---

*Fonti incrociate: [PRODUCT_BLUEPRINT.md](PRODUCT_BLUEPRINT.md) (visione integrale), [STATE_MACHINES.md](STATE_MACHINES.md) (workflow), [DOMAIN_GLOSSARY.md](DOMAIN_GLOSSARY.md) (mapping termini), [FEATURE_STATUS.md](FEATURE_STATUS.md) (stato implementazione).*
