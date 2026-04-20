import hashlib

class HashService:
    """
    Servizio per il calcolo di hash di file e integrità.
    """
    
    @staticmethod
    def calculate_sha256(file_obj):
        """
        Calcola l'hash SHA256 di un file Django UploadedFile in modo efficiente.
        """
        sha256_hash = hashlib.sha256()
        
        # Se il file è già stato letto, torniamo all'inizio
        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)
            
        # Leggiamo a pezzetti (Django default chunk size è 64KB)
        for chunk in file_obj.chunks():
            sha256_hash.update(chunk)
            
        # Riportiamo il puntatore all'inizio per permettere il salvataggio o altri processi
        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)
            
        return sha256_hash.hexdigest()
