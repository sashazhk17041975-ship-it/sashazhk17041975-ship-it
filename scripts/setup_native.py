"""Configure a local MySQL instance; never retain its administrative password."""
import getpass
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

import MySQLdb
from dotenv import dotenv_values
from native_backend import backend_for

ROOT = Path(__file__).resolve().parent.parent


def initialize_config(path):
    if path.exists():
        return False
    values = {
        'DJANGO_SECRET_KEY': secrets.token_urlsafe(64),
        'DJANGO_DEBUG': 'false',
        'DJANGO_ALLOWED_HOSTS': 'localhost,127.0.0.1',
        'DJANGO_CSRF_TRUSTED_ORIGINS': '',
        'DJANGO_HTTPS': 'false',
        'MYSQL_DATABASE': 'autoparts',
        'MYSQL_USER': 'autoparts',
        'MYSQL_PASSWORD': secrets.token_urlsafe(32),
        'DB_HOST': '127.0.0.1',
        'DB_PORT': '3306',
        'DJANGO_SUPERUSER_USERNAME': 'admin',
        'DJANGO_SUPERUSER_EMAIL': '',
        'DJANGO_SUPERUSER_PASSWORD': secrets.token_urlsafe(24),
    }
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as file:
        file.write(''.join(f'{key}={value}\n' for key, value in values.items()))
    return True


def database_config(values):
    database = values.get('MYSQL_DATABASE', '')
    user = values.get('MYSQL_USER', '')
    if not re.fullmatch(r'[A-Za-z0-9_]{1,64}', database):
        raise ValueError('MYSQL_DATABASE must contain 1-64 letters, digits or underscores.')
    if not re.fullmatch(r'[A-Za-z0-9_]{1,32}', user) or user.lower() == 'root':
        raise ValueError('MYSQL_USER must be a separate application account, not root.')
    if not values.get('MYSQL_PASSWORD'):
        raise ValueError('Set MYSQL_PASSWORD in .env.')
    host = values.get('DB_HOST', '127.0.0.1')
    if host not in ('localhost', '127.0.0.1'):
        raise ValueError('This installer configures local MySQL only. Set DB_HOST=127.0.0.1.')
    port = int(values.get('DB_PORT', '3306'))
    if not 1 <= port <= 65535:
        raise ValueError('DB_PORT must be between 1 and 65535.')
    return {'host': '127.0.0.1', 'port': port, 'user': user,
            'passwd': values['MYSQL_PASSWORD'], 'db': database,
            'charset': 'utf8mb4', 'connect_timeout': 5}


def prepare_database(config, admin_password=None):
    """Preserve existing passwords and records; only grant privileges on this DB."""
    database = config['db']
    if not re.fullmatch(r'[A-Za-z0-9_]{1,64}', database):
        raise ValueError('Invalid database identifier.')
    try:
        connection = MySQLdb.connect(**config)
    except MySQLdb.OperationalError as error:
        if error.args[0] in (2002, 2003, 2005):
            raise ValueError('Cannot reach MySQL. Start its Windows service and check DB_HOST/DB_PORT in .env.') from None
    else:
        connection.close()
        return False

    password = admin_password if admin_password is not None else getpass.getpass('MySQL root password (not saved, input is hidden): ')
    admin_options = {k: v for k, v in config.items() if k not in ('user', 'passwd', 'db')}
    admin = MySQLdb.connect(**admin_options, user='root', passwd=password)
    try:
        with admin.cursor() as cursor:
            cursor.execute("SELECT 1 FROM mysql.user WHERE User=%s AND Host='127.0.0.1'", (config['user'],))
            if cursor.fetchone():
                # Do not change another account's existing password.
                probe_options = {k: v for k, v in config.items() if k != 'db'}
                try:
                    probe = MySQLdb.connect(**probe_options)
                    probe.close()
                except MySQLdb.OperationalError:
                    raise ValueError('The application MySQL account already exists with different credentials. Set its correct MYSQL_PASSWORD in .env or choose an unused MYSQL_USER; no password was reset.') from None
            else:
                cursor.execute("CREATE USER %s@'127.0.0.1' IDENTIFIED BY %s", (config['user'], config['passwd']))
            # Identifier was checked before use; values are bound as parameters.
            cursor.execute(f'CREATE DATABASE IF NOT EXISTS `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
            cursor.execute(f"GRANT ALL PRIVILEGES ON `{database}`.* TO %s@'127.0.0.1'", (config['user'],))
    finally:
        admin.close()
    probe = MySQLdb.connect(**config)
    probe.close()
    return True


def main():
    path = ROOT / '.env'
    if initialize_config(path):
        print('Created local .env. Secret values are not displayed.')
    else:
        print('Existing .env preserved.')
    values = {key: value for key, value in dotenv_values(path).items() if value is not None}
    config = database_config(values)
    if prepare_database(config):
        print('Local database and application account prepared.')
    else:
        print('Existing database connection works; records and credentials preserved.')
    environment = dict(os.environ, **values)
    environment['DB_HOST'] = config['host']
    backend, version = backend_for(environment)
    print('Detected MySQL:', version, 'backend:', backend)
    if backend == 'mysql57':
        if values.get('AUTOPARTS_BACKEND') != 'mysql57':
            # Preserve all existing credentials; remember this schema if MySQL is upgraded later.
            with path.open('a', encoding='utf-8') as file:
                file.write('\nAUTOPARTS_BACKEND=mysql57\n')
        subprocess.run([sys.executable, '-m', 'mysql57'], cwd=ROOT, env=environment, check=True)
        print('Setup complete for MySQL 5.7. Start start-windows-native.cmd.')
        return
    for arguments in [
        ['migrate', '--noinput'], ['collectstatic', '--noinput'],
        ['bootstrap_admin'], ['seed_catalog'], ['check'],
    ]:
        subprocess.run([sys.executable, str(ROOT / 'manage.py'), *arguments],
                       cwd=ROOT, env=environment, check=True)
    print('Setup complete. Start start-windows-native.cmd. Initial admin password is in .env.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, MySQLdb.Error, OSError) as error:
        print(f'Setup failed: {error}', file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError:
        print('A setup command failed. See its output above.', file=sys.stderr)
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        print('\nSetup cancelled.', file=sys.stderr)
        sys.exit(1)
