"""Run the application locally using Waitress, including on Windows."""
import os
import argparse
import ipaddress
import re
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from native_backend import backend_for

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def local_ipv4_addresses():
    """Find addresses assigned to this machine without contacting outside services."""
    try:
        records = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        return []
    addresses = set()
    for record in records:
        address = ipaddress.IPv4Address(record[4][0])
        if not (address.is_loopback or address.is_unspecified or address.is_link_local):
            addresses.add(str(address))
    return sorted(addresses)


def main():
    from dotenv import load_dotenv
    from waitress import serve

    if not (ROOT / '.env').exists():
        raise ValueError('Run install-windows-native.cmd first; .env is missing.')
    load_dotenv(ROOT / '.env', override=True)
    if os.environ.get('DB_HOST') == 'localhost':
        os.environ['DB_HOST'] = '127.0.0.1'
    parser = argparse.ArgumentParser(description='Run AutoAnalogs locally without Docker.')
    parser.add_argument('--port', type=int, default=int(os.environ.get('APP_PORT', '8000')))
    parser.add_argument('--no-browser', action='store_true')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--lan', action='store_true', help='Allow connections from other computers on the local network.')
    mode.add_argument('--public-host', help='HTTPS hostname supplied by the internet tunnel launcher.')
    arguments = parser.parse_args()
    host, port = ('0.0.0.0' if arguments.lan else '127.0.0.1'), arguments.port
    if not 1 <= port <= 65535:
        raise ValueError('APP_PORT must be between 1 and 65535.')
    url = f'http://localhost:{port}'
    if arguments.public_host:
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com', arguments.public_host):
            raise ValueError('Expected the HTTPS hostname of a Cloudflare Quick Tunnel.')
        url = f'https://{arguments.public_host}'
        os.environ['DJANGO_ALLOWED_HOSTS'] = arguments.public_host
        os.environ['DJANGO_CSRF_TRUSTED_ORIGINS'] = url
        os.environ['DJANGO_HTTPS'] = 'true'
        os.environ['DJANGO_DEBUG'] = 'false'
    # Fail before opening a browser if another program is already on this port.
    with socket.socket() as probe:
        probe.bind((host, port))
    addresses = local_ipv4_addresses() if arguments.lan else []
    if arguments.lan:
        allowed = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
        allowed = list(dict.fromkeys(allowed + ['localhost', '127.0.0.1', socket.gethostname()] + addresses))
        os.environ['DJANGO_ALLOWED_HOSTS'] = ','.join(allowed)
    backend, version = backend_for(os.environ)
    if backend == 'mysql57':
        from mysql57.app import create_app
        from mysql57.models import db, User
        from sqlalchemy import select
        application = create_app({'SESSION_COOKIE_SECURE': True, 'REQUIRE_HTTPS': True, 'TRUSTED_HOSTS': [arguments.public_host]} if arguments.public_host else None)
        with application.app_context():
            db.session.execute(select(User.id).limit(1)).first()
    else:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autoparts.settings')
        from django.core.wsgi import get_wsgi_application
        from django.db import connection
        application = get_wsgi_application()
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1 FROM django_migrations LIMIT 1')
            cursor.fetchone()
        connection.close()
    print('MySQL:', version, 'backend:', backend)

    def open_browser():
        for _ in range(30):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=0.3):
                    webbrowser.open(url)
                    return
            except OSError:
                time.sleep(0.2)

    if not arguments.no_browser:
        threading.Thread(target=open_browser, daemon=True).start()
    print(f'AutoAnalogs: {url}. Keep this window open; press Ctrl+C to stop.', flush=True)
    if arguments.lan:
        print('Local network access enabled. Other computers can open:', flush=True)
        for address in addresses:
            print(f'  http://{address}:{port}', flush=True)
        if not addresses:
            print(f'  Run ipconfig and use your Ethernet/Wi-Fi IPv4 address with port {port}.', flush=True)
        print('Windows: allow this port on Private networks (LocalSubnet). See WINDOWS-NATIVE.md.', flush=True)
    proxy = {'trusted_proxy': '127.0.0.1', 'trusted_proxy_headers': {'x-forwarded-proto'}} if arguments.public_host else {}
    serve(application, host=host, port=port, threads=4, clear_untrusted_proxy_headers=True, **proxy)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nApplication stopped. Database records are preserved.')
    except Exception as error:
        print(f'Startup failed: {error}. Check the MySQL service and run install-windows-native.cmd.', file=sys.stderr)
        sys.exit(1)
