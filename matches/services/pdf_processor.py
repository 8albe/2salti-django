import os
import subprocess
import logging
import shutil
from typing import List, Optional
from django.conf import settings

logger = logging.getLogger(__name__)

class PDFProcessorError(Exception):
    """Eccezione base per errori nel processamento PDF."""
    pass

class PDFInvalidError(PDFProcessorError):
    """File PDF non valido o corrotto."""
    pass

class PDFConversionError(PDFProcessorError):
    """Errore durante la conversione in immagini."""
    pass

class PDFProcessor:
    """
    Servizio per la validazione e conversione di file PDF in immagini.
    Utilizza poppler-utils (pdfinfo, pdftoppm) per massima efficienza.
    """

    @staticmethod
    def is_valid(pdf_path: str) -> bool:
        """
        Verifica se il file PDF è valido e leggibile usando 'pdfinfo'.
        """
        if not os.path.exists(pdf_path):
            logger.error(f"File non trovato: {pdf_path}")
            return False

        try:
            # pdfinfo ritorna 0 se il PDF è valido, >0 altrimenti
            result = subprocess.run(
                ['pdfinfo', pdf_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.warning(f"File PDF non valido ({pdf_path}): {e.stderr.strip()}")
            return False
        except Exception as e:
            logger.error(f"Errore durante la validazione PDF: {str(e)}")
            return False

    @staticmethod
    def convert_to_images(pdf_path: str, output_dir: Optional[str] = None, dpi: int = 150) -> List[str]:
        """
        Converte un PDF in una serie di immagini JPEG (una per pagina).
        Restituisce la lista dei path delle immagini generate.
        """
        if not PDFProcessor.is_valid(pdf_path):
            raise PDFInvalidError(f"Il file {pdf_path} non è un PDF valido o è corrotto.")

        # Gestione directory di output
        if not output_dir:
            # Default: subdirectory in media/ocr_outputs/
            base_name = os.path.basename(pdf_path).split('.')[0]
            output_dir = os.path.join(settings.MEDIA_ROOT, 'ocr_outputs', base_name)
        
        os.makedirs(output_dir, exist_ok=True)

        try:
            # pdftoppm [options] PDF-file image-root
            # -jpeg: genera file jpeg
            # -r: dpi (default 150 è un buon compromesso tra qualità e velocità)
            image_root = os.path.join(output_dir, 'page')
            
            subprocess.run(
                ['pdftoppm', '-jpeg', '-r', str(dpi), pdf_path, image_root],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )

            # Recupera la lista dei file generati
            generated_files = sorted([
                os.path.join(output_dir, f) 
                for f in os.listdir(output_dir) 
                if f.startswith('page-') and f.endswith('.jpg')
            ])

            if not generated_files:
                raise PDFConversionError("Nessuna immagine generata durante la conversione.")

            logger.info(f"PDF convertito con successo: {len(generated_files)} pagine in {output_dir}")
            return generated_files

        except subprocess.CalledProcessError as e:
            logger.error(f"Errore pdftoppm: {e.stderr.strip()}")
            raise PDFConversionError(f"Errore durante la conversione PDF: {e.stderr.strip()}")
        except Exception as e:
            logger.error(f"Errore imprevisto durante la conversione PDF: {str(e)}")
            raise PDFConversionError(f"Errore di sistema: {str(e)}")

    @staticmethod
    def clean_output(output_dir: str):
        """Rimuove la directory di output e il suo contenuto."""
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
            logger.info(f"Directory di output rimossa: {output_dir}")
