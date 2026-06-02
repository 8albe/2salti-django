## 10. Subscription e piani (three-tier)

Stato: 🔄 In corso

Implementazione Freemium / Premium / Club Pro come da blueprint §6. Attualmente solo INACTIVE/ACTIVE.

### 10.1 Modello dati

- [x] `User.subscription_status` con valori INACTIVE/ACTIVE
- [x] `User.subscription_end_date`
- [ ] Modello `Subscription` separato (non più 2 CharField su `User`)
- [ ] Enum FREEMIUM / PREMIUM_USER / CLUB_PRO

### 10.2 Wiring pagamenti e gating

- [ ] Integrazione provider pagamenti (Stripe o PayPal)
- [ ] Gating feature server-side per piano (Chatbot, Live Alerts, Media upload, Recap PDF)
- [ ] Pricing definitivo Premium Utente e Club Pro (bloccato — validazione product owner)
- [ ] Modello revenue projection (stima ricavi annui per piano)

### 10.3 User Onboarding

- [x] `OnboardingMiddleware` redirect per stato logico
- [x] Property calcolata `User.onboarding_state` (aggrega `identity_status`, `subscription_status`, `setup_completed`)
- [x] Viste `verify_identity`, `process_payment`, `setup_wizard`, `onboarding_membership`
- [x] Flusso 4 step implementato (claim + team auth inglobati in MEMBERSHIP_PENDING)
- [ ] Allineamento al blueprint §7.2 con 6 step distinti (claim profilo + autenticazione squadra come step separati)

### 10.4 Identity Verification

- [x] Campo `User.identity_status` (UNVERIFIED/VERIFIED) + `User.identity_verified_at`
- [x] Vista `verify_identity()` manuale via admin
- [ ] Integrazione SPID/CIE come metodo primario (blueprint §7.3)
- [ ] Fallback documento + selfie / video-selfie per casi eccezionali

### 10.5 Membership Management

- [x] Modelli `Membership`, `MembershipRequest`, `ActivationCode`
- [x] Tre percorsi ingresso: codice attivazione, richiesta manuale, creazione admin
- [x] Workflow approvazione `MembershipRequest` (PENDING/APPROVED/REJECTED) — vedi STATE_MACHINES.md §5
- [x] Ruoli membership tipizzati (PLAYER, HEAD_COACH, ecc.) con flag `is_active`

---

← [Macro precedente](9_sistema_sponsor.md) | → [Macro successiva](11_media_gallery.md)
