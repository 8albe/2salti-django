# 2salti Project Rules & Principles

## Principi Tecnici e di Architettura
- **Django Core**: L'intera piattaforma è costruita su architettura Django; mantenere coerenza con i pattern del framework.
- **Framework Multi-sport**: Architettura, naming, database e navigazione devono essere agnostici (non limitati alla pallanuoto) per permettere l'espansione a nuovi sport senza riscritture.
- **Null invece di invenzione**: Se l'OCR o l'AI non leggono un dato con certezza, devono restituire `null`. È vietato "indovinare" o allucinare informazioni.
- **Tracciabilità Totale**: Ogni dato visualizzato deve essere sempre riconducibile al match e al referto sorgente (originale, estratto o digitale).
- **Idempotenza**: Ogni processo di ingestione o calcolo statistiche deve poter essere rieseguito senza creare duplicati o incoerenze.
- **Single Source of Truth**: Le pagine pubbliche devono derivare direttamente dallo stesso motore dati usato dall'admin; nessuna logica duplicata.

## Principi di Prodotto e UX
- **Distinzione Ospite vs Loggato**: 
    - **Guest**: Accesso a home, classifiche, risultati, statistiche generali e profili pubblici (sola lettura).
    - **Autenticato**: Accesso a dashboard personale, claim del profilo, strumenti operativi di ruolo e aree private di squadra.
- **Profili vs Account**: I profili sportivi (atleti, coach, arbitri) sono creati dal sistema. Gli utenti registrano un account e ne "reclamano" il possesso (Claim System).
- **Design System Premium**: Estetica moderna e pulita (palette Blue/Navy/Teal), supporto nativo Dark/Light mode, componenti arrotondati e micro-animazioni.
- **Mobile First**: Le tabelle dati e i tabellini devono degradare elegantemente in card o feed leggibili su dispositivi mobile.
- **Stati Vuoti Curati**: Nessuna pagina deve apparire "rotta" se mancano i dati; usare placeholder e copy che spieghino lo stato del sistema.

## Principi di Sicurezza e Sicurezza del Dato
- **Zero Hallucination (AI Query)**: Le risposte AI devono basarsi esclusivamente su dati certi del database. Se l'informazione manca, il sistema deve dichiararlo.
- **Audit Log Obbligatorio**: Ogni correzione umana ai dati estratti deve lasciare traccia di: autore, timestamp, valore precedente e motivazione.
- **Doppia Verifica**: L'accesso ai dati privati richiede sia la verifica dell'identità (SPID/CIE) sia la conferma dell'appartenenza sportiva (Codice o Approvazione Club Admin).
- **Gating Visibility**: I dati sono visibili pubblicamente solo se il match è nello stato `PUBLISHED`.
- **Protezione PII**: Massima restrizione sulla visibilità di dati sensibili (Email, Cellulari, Documenti) tranne che per i ruoli autorizzati e tracciati.
