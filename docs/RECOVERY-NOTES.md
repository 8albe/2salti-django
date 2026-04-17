# Note di Recupero Tecnico - Ambiente Dev 2salti

Documentazione degli interventi di ripristino integrità eseguiti il 21 Marzo 2026.

## 1. Problemi Riscontrati
- **Modelli Mancanti**: `ActivationCode` e `MembershipRequest` erano definiti nel database ma assenti dal codice dell'app `management`, causando `ImportError`.
- **Dati Sport Incompleti**: Il record "pallanuoto" era assente dal DB, causando 404 sulle rotte dinamiche.
- **Frammentazione Bootstrap**: Il caricamento degli sport era diviso tra script orfani fuori Git (`create_sports.py`) e logiche sparse.
- **Integrità Migrazioni**: La storia delle migrazioni era corrotta (dipendenze mancanti e migrazioni applicate senza file corrispondenti).

## 2. Soluzioni Implementate
- **Consolidamento Bootstrap**: Creato il comando management `bootstrap_sports` che centralizza la creazione di tutti gli sport (Calcio, Basket, Volley, Pallanuoto) con icone e colori corretti.
- **Ripristino Modelli**: Ricostruiti i modelli `ActivationCode` e `MembershipRequest` in `management/models.py` basandosi sullo schema SQLite reale.
- **Normalizzazione UI**: Rimossi i riferimenti hardcoded a "Pallanuoto" nella Home Page, ora gestita dinamicamente dalla griglia sport.

## 3. Interventi Manuali (DB/Migrations)
Per stabilizzare l'ambiente, sono stati eseguiti i seguenti passi manuali:
1. **Riparazione Storia**: Inserita manualmente la migrazione `core.0004` nella tabella `django_migrations` per risolvere un blocco di dipendenze.
2. **Fake Application**: Rigenerata la migrazione `management.0005` e applicata con `--fake` poiché le tabelle esistevano già.
3. **Reset Admin**: Ripristinato l'accesso all'area `/admin/`.

## 4. Guida Operativa per il Bootstrap
Per inizializzare correttamente un nuovo ambiente o resettare i dati base:
```bash
# 1. Inizializza gli sport (Single Source of Truth)
python manage.py bootstrap_sports

# 2. (Opzionale) Popola con dati reali di test (Campionato Pallanuoto)
python manage.py populate_real_data
```

## 5. Note per il Futuro
- **Sincronia**: Non cancellare mai i file in `migrations/` se la migrazione risulta applicata (`[X]`) nel DB.
- **Versionamento**: Tutti i modelli devono avere un corrispondente file di migrazione sotto Git.
- **Bootstrap**: Evitare script orfani; usare sempre comandi Django management.

---
*Documento creato da Antigravity per Alberto.*
