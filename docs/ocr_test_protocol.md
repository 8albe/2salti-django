# Protocollo di Test: OCR Workflow 2salti

Questo documento definisce i criteri di validazione per i futuri referti reali integrati nel sistema.

## Obiettivo
Garantire che i dati estratti via OCR siano affidabili e che il processo di riconciliazione (abbinamento atleti/squadre) sia privo di errori critici prima della pubblicazione delle statistiche.

## 1. Campi da Valutare (Checklist)
Per ogni referto, confrontare l'estrazione OCR con l'originale:
- [ ] **Match Info**: Data, Luogo, Campionato, Squadra Casa, Squadra Trasferta.
- [ ] **Punteggio**: Risultato finale (es. 8-6) e parziali (se presenti).
- [ ] **Giocatori (Roster)**: Numero di calottina/maglia abbinato al nome.
- [ ] **Eventi**: Marcatori (Gol), Espulsioni, Note disciplinari.

## 2. Criteri di Valutazione (KPI)

| Stato | Descrizione | Azione Correttiva |
| :--- | :--- | :--- |
| **PASS** | Estrazione identica all'originale (errori < 2% su nomi). | Procedere a Validazione Automatica. |
| **WARNING** | Errori minori su nomi (es. "Rossi" diventa "Rassi") ma numeri corretti. | Richiesta revisione manuale (Admin Review). |
| **FAIL** | Punteggio errato, nomi illeggibili (> 30%) o Squadre invertite. | Scarto (Rejected) e richiesta caricamento manuale. |

## 3. Workflow di Riconciliazione (Comparison Logic)
Durante la fase di `Reconciliation`, il sistema deve segnalare:
- **Match 100%**: Atleta già presente nel database con stesso nome/numero.
- **Match Parziale**: Nome simile (fuzzy match > 85%).
- **New Player**: Atleta non presente (richiede conferma o creazione nuovo profilo).

## 4. Limiti Noti (Iniziali)
- Il sistema attuale (Mock) non legge file reali.
- La qualità della scansione influisce pesantemente sul risultato.
- Il corsivo (handwriting) è attualmente considerato "Difficult" e ad alto rischio FAIL.
