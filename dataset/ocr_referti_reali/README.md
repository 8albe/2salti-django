# Dataset Referti Reali - Convenzioni

Questa cartella contiene i referti reali utilizzati per il training e il testing del workflow OCR.

## Struttura Cartelle
Ogni referto è contenuto in una sottocartella `rXXX/`:
- `raw/`: Contiene il file originale (PDF/JPG/PNG).
- `metadata/`: Contiene `metadata.json` con la classificazione.
- `expected_output/`: (Opzionale) Contiene il JSON atteso dopo l'estrazione corretta.

## Convenzioni Metadata
Il file `metadata.json` deve contenere:
- `id`: Identificativo unico (r001, r002, ...).
- `sport`: Sport di riferimento.
- `attributes`:
    - `format`: Estensione file.
    - `quality`: high | medium | low (basato sulla risoluzione/sfocatura).
    - `difficulty`: easy | medium | hard (basato sulla complessità del layout).
    - `handwriting`: none | partial | full (presenza di testo scritto a mano).
    - `usability`: high | medium | low (quanto è facile per un umano leggere i dati).
