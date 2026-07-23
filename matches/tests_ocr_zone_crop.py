"""
Test del ritaglio per zona (matches.services.ocr_zone_crop, §8.24 stadio 2).

Testano la geometria pura (zone_box_pixels) e il ritaglio su un'immagine PIL
sintetica: nessun referto reale, nessuna PII, nessun accesso a DB. La bonta'
dell'inquadratura sui casi gold si verifica GUARDANDO i ritagli (non con un
assert): qui si blocca solo il contratto della funzione.
"""
from django.test import SimpleTestCase
from PIL import Image

from matches.services.ocr_zone_crop import (
    ZONE_FRACTIONS, zone_box_pixels, crop_zone,
)


class ZoneBoxTest(SimpleTestCase):
    def test_storia_cronometrica_is_right_portion(self):
        left, top, right, bottom = zone_box_pixels(1000, 800, "storia_cronometrica")
        fx0, fy0, fx1, fy1 = ZONE_FRACTIONS["storia_cronometrica"]
        self.assertEqual((left, top, right, bottom),
                         (round(fx0 * 1000), round(fy0 * 800), 1000, 800))
        # E' davvero la parte destra del foglio: il bordo sinistro sta nella meta'
        # destra (con un piccolo margine a sinistra per prendere il divisore della
        # tabella), e il ritaglio arriva fino al bordo destro.
        self.assertGreater(left, 400)
        self.assertEqual(right, 1000)

    def test_unknown_zone_raises(self):
        with self.assertRaises(ValueError):
            zone_box_pixels(100, 100, "nonesiste")

    def test_invalid_dimensions_raise(self):
        with self.assertRaises(ValueError):
            zone_box_pixels(0, 100, "storia_cronometrica")

    def test_box_is_non_degenerate_on_tiny_image(self):
        left, top, right, bottom = zone_box_pixels(2, 2, "storia_cronometrica")
        self.assertGreater(right, left)
        self.assertGreater(bottom, top)


class CropZoneTest(SimpleTestCase):
    def test_crop_returns_expected_size_and_does_not_mutate_source(self):
        src = Image.new("RGB", (1000, 800), "white")
        box = zone_box_pixels(1000, 800, "storia_cronometrica")
        crop = crop_zone(src, "storia_cronometrica")
        self.assertEqual(crop.size, (box[2] - box[0], box[3] - box[1]))
        # Sorgente non modificata (funzione pura).
        self.assertEqual(src.size, (1000, 800))

    def test_crop_content_matches_region(self):
        # Meta' destra rossa, meta' sinistra bianca: il ritaglio (destra) e' rosso.
        src = Image.new("RGB", (1000, 800), "white")
        for x in range(500, 1000):
            for y in range(0, 800):
                src.putpixel((x, y), (255, 0, 0))
        crop = crop_zone(src, "storia_cronometrica")
        # Un pixel ben dentro il ritaglio deve essere rosso.
        self.assertEqual(crop.getpixel((crop.size[0] // 2, crop.size[1] // 2)), (255, 0, 0))
