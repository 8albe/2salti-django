"""Data migration: decoupling onboarding ⟂ piano.

Mapping CONGELATO (design ratificato):
  subscription_status == 'ACTIVE'   -> onboarding_payment_done = True
  subscription_status == 'INACTIVE' -> onboarding_payment_done = False
``plan`` resta FREEMIUM per TUTTI: nessun premium regalato (il mock 0,50€ non è
un pagamento reale). Il premium si concede solo via entitlement_service (seam).

Le colonne subscription_status / subscription_end_date NON vengono rimosse in
questo giro (rimozione fisica differita a un deploy successivo, finestra a due
deploy per rollback sicuro su SQLite).
"""
from django.db import migrations


def forward(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    User.objects.filter(subscription_status='ACTIVE').update(onboarding_payment_done=True)
    User.objects.filter(subscription_status='INACTIVE').update(onboarding_payment_done=False)


def backward(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    User.objects.filter(onboarding_payment_done=True).update(subscription_status='ACTIVE')
    User.objects.filter(onboarding_payment_done=False).update(subscription_status='INACTIVE')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_plan_onboarding_db_default'),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
