import os
import django
import sys
import secrets
import string

# Setup environment for 2salti-dev
NEW_BACKEND_PATH = '/opt/2salti-dev/backend'
sys.path.insert(0, NEW_BACKEND_PATH)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from accounts.models import User

def rotate_password():
    username = 'admin_dev'
    # Generate a random strong password
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    new_password = ''.join(secrets.choice(alphabet) for i in range(24))
    
    try:
        user = User.objects.get(username=username)
        user.set_password(new_password)
        user.save()
        print(f"✅ Password for '{username}' has been rotated to a random secure string.")
        print(f"ℹ️ The operator can reset it using: python manage.py changepassword {username}")
    except User.DoesNotExist:
        print(f"❌ User '{username}' not found. No rotation performed.")

if __name__ == '__main__':
    rotate_password()
