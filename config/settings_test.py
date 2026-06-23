"""Test-only settings: inherit the project config but swap the static files
storage for the non-manifest backend.

Rationale (Macro 17.1 Fase 1): dev/prod use ``ManifestStaticFilesStorage``,
which resolves ``{% static %}`` through ``staticfiles.json`` — a manifest built
by ``collectstatic``. The test runner never runs ``collectstatic``, so every
template touching ``{% static %}`` raised ``ValueError: Missing staticfiles
manifest entry`` while rendering. Tests don't need fingerprinting — they only
need ``{% static %}`` to resolve to a URL — so we point the test environment at
the plain ``StaticFilesStorage``.

This overrides ONLY the ``staticfiles`` backend; everything else is inherited
unchanged. ``config/settings.py`` (protected) is not modified, and the manifest
storage stays active for dev/prod.

Auto-selected by ``manage.py`` when ``test`` is in argv; can also be forced with
``python manage.py test --settings=config.settings_test``.
"""
from .settings import *  # noqa: F401,F403

STORAGES = {
    **STORAGES,  # noqa: F405 — inherited from config.settings
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
