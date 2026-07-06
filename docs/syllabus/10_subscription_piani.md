## 10. Subscription e piani (three-tier)

Stato: 🔄 In corso

Implementazione Freemium / Premium / Club Pro come da blueprint §6.

### 10.1 Modello dati

- [x] `User.plan` (FREEMIUM/PREMIUM) + `Society.tier` (FREE/CLUB_PRO) + `Society.is_comped`, governati dal seam `core/services/entitlement_service.py` (`User.subscription_status`/`subscription_end_date` droppati in `accounts/migrations/0011`)
- [ ] Modello `Subscription` separato (non più 2 CharField su `User`)
- [ ] Enum piani — UTENTI: FREEMIUM / PREMIUM_USER; SOCIETÀ: CLUB_PRO (a pagamento)

### 10.2 Wiring pagamenti e gating

- [ ] Integrazione provider pagamenti → scorporata nella [Macro 19 — Monetizzazione Stripe](19_monetizzazione_stripe.md) (🧊 differita, trigger e seam dormienti registrati lì)
- [ ] Gating feature server-side per piano (Chatbot, Live Alerts, Recap PDF)
- [ ] Pricing definitivo Premium Utente e Club Pro (bloccato — validazione product owner)
- [ ] Modello revenue projection (stima ricavi annui per piano)
- [ ] Eccezione pilota: Zero9 comped (no Club Pro), ricavi da sponsor — escludere dal modello revenue Club Pro

### 10.3 User Onboarding

- [x] `OnboardingMiddleware` redirect per stato logico
- [x] Property calcolata `User.onboarding_state` (aggrega `identity_status`, `setup_completed`; `onboarding_payment_done` resta sul modello per audit ma non gating)
- [x] Viste `verify_identity`, `setup_wizard`, `onboarding_membership` (`process_payment` resta solo come redirect neutro per non rompere link/bookmark esistenti: lo step pagamento onboarding è rimosso dal funnel, differito alla [Macro 19](19_monetizzazione_stripe.md))
- [x] Flusso 3 step implementato (identity, setup, membership — claim + team auth inglobati in MEMBERSHIP_PENDING; step pagamento rimosso dal funnel)
- [ ] Allineamento al blueprint §7.2 con 6 step distinti (claim profilo + autenticazione squadra come step separati)

### 10.4 Identity Verification

- [x] Campo `User.identity_status` (UNVERIFIED/VERIFIED) + `User.identity_verified_at`
- [x] Vista `verify_identity()` — pagina "controlla la tua casella" con reinvio
- [ ] ~~Integrazione SPID/CIE come metodo primario~~ **Accantonato (pivot 2026-06-19): SPID/CIE abbandonato per attrito.**
- [x] Verifica identità a click su email (invio link → conferma → `identity_status=VERIFIED`; token stateless firmato, validità 7 giorni, `accounts/services/email_verification.py`)

### 10.5 Membership Management

- [x] Modelli `Membership`, `MembershipRequest`, `ActivationCode`
- [x] Tre percorsi ingresso: codice attivazione, richiesta manuale, creazione admin
- [x] Workflow approvazione `MembershipRequest` (PENDING/APPROVED/REJECTED) — vedi STATE_MACHINES.md §5
- [x] Ruoli membership tipizzati (PLAYER, HEAD_COACH, ecc.) con flag `is_active`

---

← [Macro precedente](9_sistema_sponsor.md) | → [Macro successiva](12_live_alerts.md)
