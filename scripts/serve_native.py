"""Run the application locally using Waitress, including on Windows."""
import os
import argparse
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


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
    arguments = parser.parse_args()
    host, port = '127.0.0.1', arguments.port
    if not 1 <= port <= 65535:
        raise ValueError('APP_PORT must be between 1 and 65535.')
    url = f'http://localhost:{port}'
    # Fail before opening a browser if another program is already on this port.
    with socket.socket() as probe:
        probe.bind((host, port))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autoparts.settings')
    from django.core.wsgi import get_wsgi_application
    from django.db import connection
    application = get_wsgi_application()
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1 FROM django_migrations LIMIT 1')
        cursor.fetchone()
    connection.close()

    def open_browser():
        for _ in range(30):
            try:
                with socket.create_connection((host, port), timeout=0.3):
                    webbrowser.open(url)
                    return
            except OSError:
                time.sleep(0.2)

    if not arguments.no_browser:
        threading.Thread(target=open_browser, daemon=True).start()
    print(f'AutoAnalogs: {url}. Keep this window open; press Ctrl+C to stop.', flush=True)
    serve(application, host=host, port=port, threads=4, clear_untrusted_proxy_headers=True)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nApplication stopped. Database records are preserved.')
    except Exception as error:
        print(f'Startup failed: {error}. Check the MySQL service and run install-windows-native.cmd.', file=sys.stderr)
        sys.exit(1)
