import os
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).resolve().parent.parent / '.env')

# Base
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ['SECRET_KEY']

DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

ALLOWED_HOSTS = [h.strip() for h in os.getenv('ALLOWED_HOSTS', '').split(',') if h.strip()]

# Apps
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'crispy_forms',
    'crispy_tailwind',

    # tue app
    'accounts',
    'core',
    'matches',
    'seasons',
    'management',
]

# Crispy Forms (Tailwind)
CRISPY_ALLOWED_TEMPLATE_PACKS = "tailwind"
CRISPY_TEMPLATE_PACK = "tailwind"

# Middleware
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'accounts.middleware.OnboardingMiddleware',
]

ROOT_URLCONF = 'config.urls'

# Templates
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password
AUTH_PASSWORD_VALIDATORS = []

# International
LANGUAGE_CODE = 'it'
TIME_ZONE = 'Europe/Rome'
USE_I18N = True
USE_TZ = True

# Static
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Media
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default PK
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'accounts.User'

# Email
# §10.12-dev: in dev il backend di default è la console (le email finiscono su
# stdout), così sparisce il rumore ConnectionRefusedError quando non c'è un SMTP
# raggiungibile. Gate fail-safe: si passa a console SOLO per token di ambiente
# esplicitamente dev; qualunque altro valore — incluso "production" o
# ENVIRONMENT_NAME assente — resta sullo SMTP backend (prod invariato). Resta
# comunque sovrascrivibile via env var EMAIL_BACKEND (stessa logica env-driven).
_email_backend_default = (
    "django.core.mail.backends.console.EmailBackend"
    if os.getenv("ENVIRONMENT_NAME", "").lower() in ("development", "dev", "local")
    else "django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", _email_backend_default)
EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "25"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "False").lower() == "true"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "False").lower() == "true"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "webmaster@localhost")
SERVER_EMAIL = os.getenv("SERVER_EMAIL", DEFAULT_FROM_EMAIL)
EMAIL_TIMEOUT = 10
EMAIL_USE_LOCALTIME = True

# Logging
# Un console handler su stderr fa emergere le traceback dei 500
# (django.request ERROR) nel log di gunicorn (error.log in prod, journald in
# dev), indipendentemente da DEBUG e senza dipendere dall'invio email a
# mail_admins — la consegna SMTP è un problema separato (OPS_RUNBOOK §10.12).
# disable_existing_loggers=False per non spegnere i logger di Django/terze parti.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}

# --- OCR PROVIDER CONFIGURATION ---
# Supported providers: 'mock', 'gpt4o'
OCR_PROVIDER = os.getenv("OCR_PROVIDER", "mock")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# --- NOTIFICATIONS CONFIGURATION ---
# Email recipients for operational alerts
PILOT_EMAIL_RECIPIENTS = os.getenv("PILOT_EMAIL_RECIPIENTS", "albegalbi@gmail.com").split(",")
OPS_EMAIL_RECIPIENTS = os.getenv("OPS_EMAIL_RECIPIENTS", ",".join(PILOT_EMAIL_RECIPIENTS)).split(",")

# Telegram Configuration (Placeholder, requires bot setup)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
