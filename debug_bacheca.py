import os
import django
from django.conf import settings
from django.template import loader, Context
from django.test import RequestFactory

# Setup minimal Django
if not settings.configured:
    settings.configure(
        DEBUG=True,
        TEMPLATES=[{
            'BACKEND': 'django.template.backends.django.DjangoTemplates',
            'DIRS': [os.path.join(os.getcwd(), 'templates')],
            'APP_DIRS': True,
        }],
        INSTALLED_APPS=[
            'django.contrib.contenttypes',
            'django.contrib.auth',
            'management',
            'core',
            'accounts',
            'matches',
        ],
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:',
            }
        },
        USE_TZ=True,
    )
    django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

def test_render():
    t = loader.get_template('management/bacheca.html')
    user = User(username='testuser')
    rf = RequestFactory()
    request = rf.get('/bacheca/')
    request.user = user
    request.current_society = None
    
    context = {
        'posts': [],
        'team': None,
        'user_membership': None,
        'can_post': True,
        'is_president': True,
        'request': request,
    }
    
    try:
        rendered = t.render(context)
        print("Render successful!")
    except Exception as e:
        print(f"Render failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_render()
