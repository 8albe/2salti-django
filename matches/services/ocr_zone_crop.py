"""
Ritaglio REALE di una zona del referto (doppia estrazione per zona, §8.24 stadio 2).

Fin qui la "zona" del secondo passaggio era solo una restrizione d'attenzione via
prompt: al modello si mandava l'immagine INTERA del referto restringendo lo sguardo
a parole. Questo modulo introduce un ritaglio VERO — data l'immagine del referto,
restituisce il ritaglio di una zona nominata, definita come FRAZIONE FISSA della
pagina (il caso più semplice che funziona, non una registrazione su template).

PRESUPPOSTO delle frazioni fisse: l'immagine è ORIENTATA come un referto landscape
visto dall'alto (STORIA CRONOMETRICA a destra). È responsabilità del chiamante
passare l'immagine GIÀ preprocessata (ImagePreprocessor: EXIF fix + auto-rotate +
deskew), cioè la STESSA immagine inviata al modello. Su una foto non orientata
(sheet ruotato di 90°) la frazione fissa inquadra la zona sbagliata: normalizzare
quei casi è la registrazione su template, un progetto a sé fuori dallo scope di
questo giro.

Funzioni pure sull'immagine (PIL): nessun accesso a DB, nessun import di Django.
Il caricamento/preprocessing opzionale vive in una funzione di comodo separata.
"""
from typing import Tuple, Dict

# Zone come frazioni (x0, y0, x1, y1) del rettangolo pagina, con origine in alto a
# sinistra e valori in [0, 1]. Calibrate sui casi gold ORIENTATI (unime, olympic,
# bellator, pol-delta): la STORIA CRONOMETRICA occupa la metà destra del foglio,
# sotto la riga di intestazione, fino al bordo inferiore.
ZONE_FRACTIONS: Dict[str, Tuple[float, float, float, float]] = {
    # Play-by-play (I–IV TEMPO): dove vivono le calottine degli autori, cioè la
    # zona che serve all'identità per calottina (§8.24).
    "storia_cronometrica": (0.47, 0.11, 1.0, 1.0),
}


def zone_box_pixels(width: int, height: int, zone: str) -> Tuple[int, int, int, int]:
    """Converte la frazione della zona in un box di pixel (left, top, right, bottom).

    Il box è clampato ai bordi dell'immagine e garantito non degenere (almeno 1px
    per lato). Solleva ValueError se la zona non è nota o le dimensioni non sono valide.
    """
    if zone not in ZONE_FRACTIONS:
        raise ValueError(
            f"Zona sconosciuta: {zone!r} (disponibili: {', '.join(sorted(ZONE_FRACTIONS))})"
        )
    if width <= 0 or height <= 0:
        raise ValueError(f"Dimensioni immagine non valide: {width}x{height}")
    fx0, fy0, fx1, fy1 = ZONE_FRACTIONS[zone]
    left = max(0, min(width - 1, int(round(fx0 * width))))
    top = max(0, min(height - 1, int(round(fy0 * height))))
    right = max(left + 1, min(width, int(round(fx1 * width))))
    bottom = max(top + 1, min(height, int(round(fy1 * height))))
    return left, top, right, bottom


def crop_zone(image, zone: str):
    """Ritaglia `zone` da un'immagine PIL già orientata. Ritorna una nuova PIL.Image.

    Funzione pura: non modifica l'immagine sorgente. `image` deve esporre `.size`
    e `.crop()` (contratto PIL.Image).
    """
    width, height = image.size
    box = zone_box_pixels(width, height, zone)
    return image.crop(box)


def crop_zone_from_file(image_path: str, zone: str, out_path: str, preprocess: bool = True) -> str:
    """Comodità: carica `image_path`, (opz.) preprocessa, ritaglia `zone`, salva in `out_path`.

    Con preprocess=True passa prima da ImagePreprocessor (EXIF fix + auto-rotate +
    deskew), così il ritaglio a frazione fissa opera sull'immagine ORIENTATA, la
    stessa inviata al modello. Ritorna out_path. Import di PIL/Django locali per
    tenere il modulo importabile senza Django nei test puri di `crop_zone`.
    """
    import os
    from PIL import Image

    src = image_path
    if preprocess:
        from matches.services.image_preprocessor import ImagePreprocessor
        # ensure_landscape=True: il ritaglio a frazioni fisse presuppone un foglio
        # orizzontale; un referto rimasto verticale inquadrerebbe la zona sbagliata
        # (§8.24 stadio A). In produzione process() gira senza questo flag.
        src = ImagePreprocessor.process(image_path, ensure_landscape=True)

    with Image.open(src) as im:
        im = im.convert("RGB")
        crop = crop_zone(im, zone)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        crop.save(out_path)
    return out_path
