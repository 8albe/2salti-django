import os
import logging
import tempfile
import unittest
from unittest.mock import patch

REAL_DATASET_PATH = "/home/alberto/dataset/ocr_referti_reali"
_DATASET_AVAILABLE = os.path.isdir(REAL_DATASET_PATH)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

import cv2
import numpy as np
from PIL import Image

from matches.services.image_preprocessor import ImagePreprocessor

logger = logging.getLogger(__name__)


class ImagePreprocessorRealDataTest(unittest.TestCase):

    @unittest.skipUnless(_DATASET_AVAILABLE, "Real dataset not available on this machine")
    def test_real_image_processing(self):
        image_path = os.path.join(REAL_DATASET_PATH, "r001/raw/reale_01.jpeg")
        output_path = ImagePreprocessor.process(image_path)
        self.assertTrue(
            output_path and os.path.exists(output_path),
            f"Processed image not created or path invalid: {output_path}"
        )


class ImagePreprocessorRotationTest(unittest.TestCase):
    """
    Il referto reale può essere sia orizzontale sia verticale: la vecchia
    _auto_rotate_to_portrait (ruota se larghezza > altezza) corrompeva metà
    dei referti orizzontali mandandoli al modello coricati. Questi test
    verificano che process() non ruoti più per aspect-ratio, mantenendo però
    la correzione EXIF (fotocamera) invariata.
    """

    def setUp(self):
        fd, self.image_path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(self.image_path) and os.remove(self.image_path))

    def _write_plain_image(self, width, height, path=None):
        """
        Immagine uniforme (nessun bordo/contorno rilevabile): evita che
        _correct_perspective trovi un quadrilatero e alteri le dimensioni,
        cosi' il test isola solo il comportamento di rotazione.
        """
        path = path or self.image_path
        img = np.full((height, width, 3), 200, dtype=np.uint8)
        cv2.imwrite(path, img)
        return path

    def test_landscape_image_is_not_rotated_to_portrait(self):
        self._write_plain_image(width=1600, height=1000)
        output_path = ImagePreprocessor.process(self.image_path)
        self.addCleanup(lambda: os.path.exists(output_path) and os.remove(output_path))
        result = cv2.imread(output_path)
        h, w = result.shape[:2]
        self.assertGreater(w, h, f"L'immagine landscape è stata ruotata a portrait: {w}x{h}")

    def test_auto_rotate_to_portrait_not_invoked_by_default(self):
        self._write_plain_image(width=1600, height=1000)
        with patch(
            "matches.services.image_preprocessor.ImagePreprocessor._auto_rotate_to_portrait"
        ) as mock_rotate:
            output_path = ImagePreprocessor.process(self.image_path)
            self.addCleanup(lambda: os.path.exists(output_path) and os.remove(output_path))
        mock_rotate.assert_not_called()

    def test_exif_orientation_is_still_corrected(self):
        """La rotazione EXIF (metadati fotocamera) resta attiva: non è l'HACK by aspect-ratio."""
        fd, path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))

        img = Image.new("RGB", (100, 200), color=(150, 150, 150))
        exif = Image.Exif()
        exif[274] = 6  # Orientation tag: 6 = ruotato 90° CW dalla fotocamera
        img.save(path, exif=exif)

        fixed_path = ImagePreprocessor._fix_exif_rotation(path)
        self.addCleanup(lambda: os.path.exists(fixed_path) and os.remove(fixed_path))

        self.assertNotEqual(
            fixed_path, path,
            "Con EXIF orientation=6 ci si aspetta un file '_exif_fix' separato (rotazione applicata)."
        )
        self.assertTrue(fixed_path.endswith("_exif_fix.jpg"))
