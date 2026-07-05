from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
import os

User = get_user_model()

REQUIRED_ENV_VARS = (
    'DJANGO_SUPERUSER_USERNAME',
    'DJANGO_SUPERUSER_EMAIL',
    'DJANGO_SUPERUSER_PASSWORD',
)


class Command(BaseCommand):
    help = 'Create a superuser if none exists, reading credentials from env vars'

    def handle(self, *args, **options):
        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write('Superuser already exists.')
            return

        missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]
        if missing:
            raise CommandError(
                'Nessun superuser esistente e variabili d\'ambiente mancanti: '
                f'{", ".join(missing)}. Impostale prima di eseguire questo comando '
                '(nessun fallback debole disponibile).'
            )

        username = os.environ['DJANGO_SUPERUSER_USERNAME']
        email = os.environ['DJANGO_SUPERUSER_EMAIL']
        password = os.environ['DJANGO_SUPERUSER_PASSWORD']
        User.objects.create_superuser(username, email, password)
        self.stdout.write(self.style.SUCCESS(f'Superuser created: {username}'))
