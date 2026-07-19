## 21. App multipiattaforma (PWA-first)

Stato: ⏳ Da fare (direzione decisa 2026-07-19, non avviata)

Accesso a 2salti da tutte le piattaforme (mobile e desktop) con un'unica base web. Approccio PWA-first: prima una PWA installabile da browser, app native da store solo in fase successiva.

### 21.1 Fase 1 — PWA installabile

- [ ] Web App Manifest (nome, icone, theme color, display standalone)
- [ ] Service Worker (registrazione, caching di base)
- [ ] Installabilità da browser (Android/desktop; iOS via "Aggiungi alla schermata Home")

Zero costi di store. Sinergica con l'architettura offline-first già prevista dal referto digitale (Service Worker + IndexedDB, vedi Macro 14 §14.3): il Service Worker introdotto qui è lo stesso mattone tecnico.

### 21.2 Fase 2 — App native da store (futura, non pianificata)

Pubblicazione su store solo in fase successiva, eventualmente via wrapper sulla stessa base web. Costi: Apple Developer ~99$/anno, Google Play ~25$ una tantum. Nessun task pianificato: si apre solo a Fase 1 completata e con un bisogno reale di distribuzione via store.

---

← [Macro precedente](20_venue_impianto.md)
