## 19. Monetizzazione Stripe

Stato: 🧊 Differita (per decisione di prodotto 2026-07-06 — i seam restano dormienti e revert-ready)

Integrazione pagamenti reali via Stripe per i piani a pagamento (Premium utente, Club Pro società). Scorporata dalla Macro 10 (che resta la macro dei *piani*: modello dati, enum, gating feature) in una macro dedicata al *wiring pagamenti*: checkout, webhook, ciclo di vita subscription.

### 19.1 Trigger di attivazione

Si accende quando l'usabilità di base è raggiunta **E** arriva la prima entità disposta a pagare — società non-comped per Club Pro oppure utente per Premium. Prezzi puntuali restano TBD. I seam restano dormienti e revert-ready fino ad allora.

### 19.2 Seam già a codice, dormienti

Nessun codice Stripe esiste oggi; i punti di aggancio sono già costruiti e in produzione:

- [x] `User.onboarding_payment_done` — flag audit dello step pagamento onboarding (mock 0,50€), asse funnel separato dal piano: non gating, resta sul modello per audit
- [x] `User.plan` + `Society.tier` / `Society.is_comped` — governati esclusivamente dal seam `core/services/entitlement_service.py` (audit `ENTITLEMENT_*`); il webhook di pagamento reale si aggancerà lì (`source='stripe_webhook'`), in un punto solo (OPS_RUNBOOK §"entitlement")
- [x] Decoratore `club_pro_required` (`accounts/decorators.py`) — creato, testato, **non applicato ad alcuna view**: si applica quando il gating diventa reale
- [x] Step pagamento onboarding skippato e revert-ready — `process_payment` resta come redirect neutro (link/bookmark non rompono), il funnel è a 3 step senza pagamento

### 19.3 Scope di massima all'accensione

- [ ] Checkout Stripe (Premium utente, Club Pro società)
- [ ] Webhook pagamento → entitlement seam (`source='stripe_webhook'`)
- [ ] Ciclo di vita subscription (attivazione, rinnovo, scadenza, downgrade)
- [ ] Applicazione `club_pro_required` / gating server-side sulle feature a pagamento — sblocca il gating di Macro 10 (piani), Macro 12 (Live Alerts Premium), Macro 13 (Recap PDF)
- [ ] Pricing definitivo Premium/Club Pro (decisione product owner, TBD)
- [ ] Eccezione pilota: Zero9 comped resta fuori dal revenue Club Pro (vedi Macro 10.2)

---

← [Macro precedente](18_personificazione_societa.md) | → [Macro successiva](20_venue_impianto.md)
