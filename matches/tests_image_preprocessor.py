import os
import logging
import unittest

REAL_DATASET_PATH = "/home/alberto/dataset/ocr_referti_reali"
_DATASET_AVAILABLE = os.path.isdir(REAL_DATASET_PATH)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

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
