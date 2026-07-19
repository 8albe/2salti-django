import os
from django.conf import settings

INTEGRATION_REGISTRY = {
    'OCR': {
        'status': 'REAL' if getattr(settings, 'OCR_PROVIDER', 'mock') != 'mock' else 'SIMULATED',
        'provider': getattr(settings, 'OCR_PROVIDER', 'mock'),
        'description': 'Estrazione dati dai referti cartacei/PDF via Vision API.'
    },
    'EMAIL_INGESTION': {
        'status': 'PLACEHOLDER',
        'provider': 'Built-in (Wait for wiring)',
        'description': 'Ricezione referti via email (IMAP/Webhook).'
    },
    'NOTIFICATIONS': {
        'status': 'REAL' if not settings.EMAIL_BACKEND.endswith('ConsoleBackend') else 'MIXED',
        'provider': settings.EMAIL_BACKEND.split('.')[-1],
        'description': 'Invio email e alert di sistema.'
    },
    'IDENTITY_VERIFICATION': {
        'status': 'REAL' if not settings.EMAIL_BACKEND.endswith('ConsoleBackend') else 'MIXED',
        'provider': 'Email a click (token firmato)',
        'description': 'Verifica identità via link email firmato (accounts/services/email_verification.py).'
    },
    'PAYMENTS': {
        'status': 'PLACEHOLDER',
        'provider': 'Nessuno (step rimosso dal funnel onboarding)',
        'description': 'Abbonamenti e transazioni: nessun processore reale integrato, in attesa di Macro 10.'
    }
}
