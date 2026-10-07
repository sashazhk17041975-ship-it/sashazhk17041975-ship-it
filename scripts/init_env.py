"""Create local configuration without printing or replacing existing secrets."""
import os
import secrets
from pathlib import Path

path = Path(__file__).resolve().parent.parent / '.env'
if path.exists():
    print('.env already exists; preserved.')
else:
    values = {
        'DJANGO_SECRET_KEY': secrets.token_urlsafe(64),
        'DJANGO_DEBUG': 'false',
        'DJANGO_ALLOWED_HOSTS': 'localhost,127.0.0.1',
        'DJANGO_CSRF_TRUSTED_ORIGINS': '',
        'DJANGO_HTTPS': 'false',
        'MYSQL_DATABASE': 'autoparts',
        'MYSQL_USER': 'autoparts',
        'MYSQL_PASSWORD': secrets.token_urlsafe(32),
        'MYSQL_ROOT_PASSWORD': secrets.token_urlsafe(32),
        'DB_HOST': '127.0.0.1',
        'DB_PORT': '3306',
        'DJANGO_SUPERUSER_USERNAME': 'admin',
        'DJANGO_SUPERUSER_EMAIL': '',
        'DJANGO_SUPERUSER_PASSWORD': secrets.token_urlsafe(24),
    }
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as file:
        file.write(''.join(f'{key}={value}\n' for key, value in values.items()))
    print('Created private .env with random local secrets.')
