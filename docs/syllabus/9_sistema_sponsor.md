## 9. Sistema sponsor

Stato: 🔄 In corso

Sponsor associati a società/campionati, visualizzazione pubblica, modello dati dedicato (non solo JSONField).

### 9.1 Modello dati

- [x] `Society.sponsors` come `JSONField` flat (`[{"name", "logo_url"}]`)
- [ ] Modello `Sponsor_Assets` separato (blueprint §10, §13)
- [ ] Placement (pagina società, profilo atleta, footer)
- [ ] Targeting per stagione
- [ ] Test serializzazione sponsor (oggi nessuna copertura — FEATURE_STATUS Coverage Gaps)

### 9.2 Visualizzazione pubblica

- [ ] Render sponsor su pagina società
- [ ] Render sponsor su footer/profilo atleta secondo placement

---

← [Macro precedente](8_ocr_affidabilita.md) | → [Macro successiva](10_subscription_piani.md)
