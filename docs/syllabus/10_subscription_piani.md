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

---

← [Macro precedente](9_sistema_sponsor.md) | → [Macro successiva](11_media_gallery.md)
