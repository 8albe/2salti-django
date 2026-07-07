import cv2
import numpy as np
import logging
from PIL import Image, ExifTags
import os
import time
import math
from django.conf import settings

logger = logging.getLogger(__name__)

class ImagePreprocessor:
    """
    Servizio per il preprocessing di immagini fotografiche di referti.
    Ottimizza prospettiva, contrasto e ombre per migliorare l'estrazione OCR.
    """

    @staticmethod
    def process(image_path, output_name=None):
        """
        Processa un'immagine e restituisce il path del file preprocessato.
        Pipeline: EXIF Fix -> Perspective correction -> Deskew -> Contrast -> Resize
        """
        try:
            # 0. Fix EXIF Rotation (Pillow) prima di passare a OpenCV
            image_path = ImagePreprocessor._fix_exif_rotation(image_path)

            # Caricamento immagine (OpenCV)
            img = cv2.imread(image_path)
            if img is None:
                raise ValueError(f"Impossibile caricare l'immagine: {image_path}")

            # 1. Tentativo correzione prospettiva (fail-safe)
            # Se trova il documento, corregge anche gran parte dello skew
            processed_img = ImagePreprocessor._correct_perspective(img)
            perspective_corrected = processed_img is not img

            # 2. Deskewing (solo se non abbiamo già fatto la prospettiva, che è più potente)
            if not perspective_corrected:
                processed_img = ImagePreprocessor._deskew(processed_img)

            # 3. Resize proporzionale (max 2000px per lato per OpenAI)
            h, w = processed_img.shape[:2]
            max_dim = 2000
            if max(h, w) > max_dim:
                scale = max_dim / max(h, w)
                processed_img = cv2.resize(processed_img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

            # 4. Compensazione ombre adattiva
            processed_img = ImagePreprocessor._compensate_shadows(processed_img)

            # 5. Correzione Contrasto (CLAHE)
            final_img = ImagePreprocessor._apply_clahe(processed_img)

            # Salvataggio
            if not output_name:
                base, ext = os.path.splitext(image_path)
                output_path = f"{base}_proc.jpg"
            else:
                output_path = os.path.join(os.path.dirname(image_path), output_name)

            cv2.imwrite(output_path, final_img)
            logger.info(f"Image preprocessed successfully: {output_path} ({final_img.shape})")
            return output_path

        except Exception as e:
            logger.error(f"Errore durante il preprocessing: {str(e)}")
            return image_path

    @staticmethod
    def _compensate_shadows(img):
        """
        Compensazione ombre adattiva usando morphological closing.
        Equalizza illuminazione disomogenea tipica delle foto smartphone.
        """
        try:
            # Converti in scala di grigi per analisi
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Dilate per ottenere lo sfondo (forma chiusa morfologica)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (31, 31))
            bg = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
            
            # Dividi il grigio per lo sfondo per normalizzare l'illuminazione
            # Previeni divisione per zero
            bg_float = bg.astype(np.float32)
            bg_float[bg_float == 0] = 1.0
            
            normalized = (gray.astype(np.float32) / bg_float * 255).clip(0, 255).astype(np.uint8)
            
            # Applica il fattore di correzione ai 3 canali
            correction = (normalized.astype(np.float32) / (gray.astype(np.float32) + 1.0))
            
            # Applica la correzione all'immagine a colori
            result = img.copy().astype(np.float32)
            for c in range(3):
                result[:, :, c] = (result[:, :, c] * correction).clip(0, 255)
            
            return result.astype(np.uint8)
        except Exception as e:
            logger.warning(f"Shadow compensation fallita, uso immagine originale: {e}")
            return img

    @staticmethod
    def _correct_perspective(img):
        """
        Prova a correggere la prospettiva dell'immagine.
        Se fallisce o il contorno non è chiaro, ritorna l'immagine originale.
        """
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            blur = cv2.GaussianBlur(gray, (5, 5), 0)
            edged = cv2.Canny(blur, 75, 200)

            # Trova contorni
            cnts, _ = cv2.findContours(edged.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:5]

            for c in cnts:
                peri = cv2.arcLength(c, True)
                approx = cv2.approxPolyDP(c, 0.02 * peri, True)

                if len(approx) == 4:
                    # Verifica che il quadrilatero sia abbastanza grande (almeno 20% dell'immagine)
                    area = cv2.contourArea(approx)
                    img_area = img.shape[0] * img.shape[1]
                    if area < img_area * 0.2:
                        continue
                    
                    rect = ImagePreprocessor._order_points(approx.reshape(4, 2))
                    (tl, tr, br, bl) = rect

                    widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
                    widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
                    maxWidth = max(int(widthA), int(widthB))

                    heightA = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
                    heightB = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
                    maxHeight = max(int(heightA), int(heightB))

                    if maxWidth < 100 or maxHeight < 100:
                        continue  # Too small to be the document

                    dst = np.array([
                        [0, 0],
                        [maxWidth - 1, 0],
                        [maxWidth - 1, maxHeight - 1],
                        [0, maxHeight - 1]], dtype="float32")

                    M = cv2.getPerspectiveTransform(rect, dst)
                    warped = cv2.warpPerspective(img, M, (maxWidth, maxHeight))
                    logger.info("Correzione prospettiva applicata con successo.")
                    return warped

        except Exception as e:
            logger.warning(f"Correzione prospettiva fallita: {e}")

        return img  # Fallback

    @staticmethod
    def _fix_exif_rotation(image_path):
        """Usa PIL per ruotare l'immagine in base ai metadati EXIF."""
        try:
            img = Image.open(image_path)
            exif = img._getexif()
            if exif:
                for tag, value in exif.items():
                    decoded = ExifTags.TAGS.get(tag, tag)
                    if decoded == 'Orientation':
                        if value == 3: img = img.rotate(180, expand=True)
                        elif value == 6: img = img.rotate(270, expand=True)
                        elif value == 8: img = img.rotate(90, expand=True)
                        break
                # Sovrascrive temporaneamente o ritorna lo stesso se non serve rotazione
                # Per ora salviamo una copia corretta se necessario
                if value in [3, 6, 8]:
                    base, ext = os.path.splitext(image_path)
                    new_path = f"{base}_exif_fix{ext}"
                    img.save(new_path, quality=95)
                    return new_path
        except Exception as e:
            logger.warning(f"EXIF rotation fix failed: {e}")
        return image_path

    @staticmethod
    def _auto_rotate_to_portrait(img):
        """
        Se l'immagine è landscape, la ruota di 90 gradi assuming referto is portrait.
        NON PIU' INVOCATO da process(): i referti reali sono sia orizzontali sia
        verticali, quindi ruotare by aspect-ratio corrompeva metà dei referti
        orizzontali. Lasciato definito (non invocato) per reversibilità minima.
        """
        h, w = img.shape[:2]
        if w > h:
            logger.info("Auto-rotating image to portrait mode.")
            return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        return img

    @staticmethod
    def _deskew(img):
        """Correzione fine della rotazione basata sulle linee di testo."""
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # Inverti: testo chiaro su sfondo scuro per Hough
            gray = cv2.bitwise_not(gray)
            thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
            
            coords = np.column_stack(np.where(thresh > 0))
            angle = cv2.minAreaRect(coords)[-1]
            
            # cv2.minAreaRect returns angle in range [-90, 0)
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle
                
            if abs(angle) < 0.1 or abs(angle) > 10:
                return img # No skew or too much skew (potentially wrong detection)

            (h, w) = img.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
            logger.info(f"Deskew applied: {angle:.2f} degrees")
            return rotated
        except Exception as e:
            logger.warning(f"Deskew failed: {e}")
            return img

    @staticmethod
    def _apply_clahe(img):
        """Applica CLAHE per il contrasto bilanciato."""
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        cl = clahe.apply(l)
        limg = cv2.merge((cl, a, b))
        return cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)

    @staticmethod
    def _order_points(pts):
        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]
        return rect
