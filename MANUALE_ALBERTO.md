# MANUALE ALBERTO - 2salti legacy

## 👋 Benvenuto nel tuo Progetto
**2salti** è il sistema definitivo per la gestione dei campionati sportivi.
Questo documento è la tua guida rapida allo stato del progetto, alle funzionalità e ai prossimi passi.

---

## 🎯 Visione del Prodotto
Il sistema non è solo un sito di risultati, ma una **piattaforma gestionale**.
L'obiettivo è automatizzare il flusso:
1.  L'Arbitro/Admin inserisce il referto.
2.  Il sistema valida i dati.
3.  Le classifiche e le statistiche dei giocatori si aggiornano **da sole**.

---

## 👥 I Ruoli (Chi fa cosa)

| Ruolo | Cosa può fare |
| :--- | :--- |
| **Atleta** | Vedere statistiche, seguire squadre, RSVP allenamenti, vedere bacheca. |
| **Allenatore** | Gestire la rosa, creare allenamenti, inviare convocazioni, postare in bacheca. |
| **Arbitro** | Inserire i risultati (Referto digitale), vedere lo storico partite. |
| **Presidente** | Gestire la Società, creare post broadcast, visibilità totale su tutte le squadre. |
| **Admin** | (Tu/Superuser) Controllo totale, validazione dati, creazione campionati. |

---

## 🎨 Struttura e Layout (Design System)

Il sito utilizza un design "Premium Neon Dark" con due modalità principali di visualizzazione delle partite:

### 1. Home Page Generale
La vetrina principale del sito.
-   **Hero Section**: Grande banner emozionale ("Il Tuo Sport, Un Altro Livello").
-   **Griglia Sport**: Lista degli sport disponibili (Calcio, Basket, Pallanuoto, ecc.) visualizzati come card.
-   **Nota**: In questa pagina *non* vengono mostrate le partite, per manterere la pulizia visiva e indirizzare l'utente verso lo sport specifico.

### 2. Home Sport (es. `/sport/pallanuoto`)
La dashboard per lo sport specifico.
-   **Lista Compatta (Schedule)**: Le partite sono mostrate in una lista "Ultra-Compact" (altezza righe 40px).
-   **Raggruppamento**: Le partite sono divise per Campionato (Serie A1, A2, ecc.).
-   **Funzionalità**: Include il selettore data (calendario).

### 3. Pagina Squadra (Team Detail)
Il cuore del tifo.
-   **Tabellino Prossimo Turno**: Una "Match Card" grande ed evidenziata che mostra il prossimo incontro, con data, orario, loghi grandi e link per le indicazioni stradali.
-   **Storico Partite**: Lista compatta (come lo sport home) delle ultime partite giocate.

### 4. Profilo Utente
-   **Liste Partite**: Tutte le liste (Partite Recenti, Partite Squadra, Partite Arbitrate) utilizzano il formato **Lista Compatta** per coerenza.

### Componenti Tecnici Implementati
-   **Compact Match Row**: Componente riutilizzabile (`compact_match_row.html`) per le liste dense.
-   **Date Picker**: Calendario orizzontale scorrevole per filtrare i match.
-   **Google Maps Integration**: I campi "Luogo" nelle partite generano automaticamente link a Google Maps.

### 5. Bacheca e Comunicazione
- **Bacheca di Squadra**: Post pinnati per avvisi importanti, commenti per coordinamento.
- **Broadcast Societari**: Messaggi del Presidente visibili a tutti i membri della società.
- **Chat di Squadra**: Messaggistica istantanea interna alla squadra.

### 6. Gestione Allenamenti e Convocazioni
- **Calendario Allenamenti**: Visibile a tutti gli atleti della società.
- **RSVP con Geofencing**: Gli atleti confermano la presenza; il sistema valida la posizione (120m dal campo).
- **Convocazioni Smart**: Gli allenatori possono riutilizzare il setup dell'ultima partita per velocizzare l'invio.

---

## 🚀 Stato Attuale del Progetto (Cosa c'è)

### ✅ Backend & Infrastruttura
- Il "motore" è pronto e gira su **2salti.com**.
- **Stagione Attiva**: 2025/2026 configurata.
- Sistema di ruoli avanzato (Membership RBAC) implementato.

### ✅ Funzionalità Gestionali
- **Bacheca**: Sistema di post e commenti attivo.
- **Allenamenti**: Gestione ricorrenze e RSVP funzionante.
- **Convocazioni**: Flusso creazione e pubblicazione attivo.

### ✅ Frontend & Design
- **Theme**: "Premium Neon Dark" (Neon Glow & Glassmorphism) su tutto il sito.
- **Responsive**: Ottimizzato per Mobile (Menu non sovrapposto, tabelle scrollabili).

---

## 📅 Roadmap (Prossimi Passi per Noi)

1.  **Ottimizzazione SEO**: Monitoraggio posizionamento dopo il cambio dominio in `2salti.com`.
2.  **Monitoraggio Statistiche**: Tuning dei servizi di calcolo automatico.
3.  **Nuove Feature**: Implementazione di eventuali richieste specifiche (es. Pagamenti/Quote).