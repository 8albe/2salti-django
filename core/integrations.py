import os
from django.conf import settings

INTEGRATION_REGISTRY = {
    'OCR': {
        'status': 'REAL' if getattr(settings, 'OCR_PROVIDER', 'mock') == 'gpt4o' else 'SIMULATED',
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
        'status': 'SIMULATED',
        'provider': 'Mock SPID/CIE',
        'description': 'Verifica identità legale tramite gateway nazionale.'
    },
    'PAYMENTS': {
        'status': 'SIMULATED',
        'provider': 'Mock Stripe/PayPal',
        'description': 'Gestione abbonamenti e transazioni.'
    }
}
