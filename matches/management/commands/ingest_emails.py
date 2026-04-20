import os
from django.core.management.base import BaseCommand
from matches.services.email_ingestion import EmailIngestionService

class Command(BaseCommand):
    help = 'Processa file .eml da una directory e crea MatchReport.'

    def add_arguments(self, parser):
        parser.add_argument('--dir', type=str, help='Directory contenente i file .eml', required=True)
        parser.add_argument('--delete', action='store_true', help='Elimina i file .eml processati con successo')

    def handle(self, *args, **options):
        directory = options['dir']
        delete_after = options['delete']

        if not os.path.isdir(directory):
            self.stderr.write(self.style.ERROR(f"Directory non valida: {directory}"))
            return

        eml_files = [f for f in os.listdir(directory) if f.lower().endswith('.eml')]
        
        if not eml_files:
            self.stdout.write(self.style.WARNING("Nessun file .eml trovato."))
            return

        self.stdout.write(f"Inizio processamento di {len(eml_files)} file .eml...")
        
        for filename in eml_files:
            file_path = os.path.join(directory, filename)
            self.stdout.write(f"Processando {filename}...", ending='')
            
            try:
                results = EmailIngestionService.process_eml_file(file_path)
                
                new_reports = [r for r, created in results if created]
                existing_reports = [r for r, created in results if not created]
                
                if not results:
                    self.stdout.write(self.style.WARNING(" [SKIP] Nessun allegato valido trovato."))
                else:
                    msg = f" [OK] Creati {len(new_reports)} nuovi report, {len(existing_reports)} già presenti."
                    self.stdout.write(self.style.SUCCESS(msg))
                
                if delete_after:
                    os.remove(file_path)
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f" [ERR] {str(e)}"))
        
        self.stdout.write(self.style.SUCCESS("Processamento terminato."))
