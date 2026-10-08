"""Supervise a temporary Cloudflare HTTPS tunnel and the local web server."""
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOWNLOAD_URL = 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe'
TUNNEL_URL = re.compile(r'https://([a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com)(?![a-z0-9.-])')


def find_cloudflared():
    for name in ('cloudflared-windows-amd64.exe', 'cloudflared.exe'):
        candidate = ROOT / name
        if candidate.is_file():
            return candidate
    raise ValueError(f'Download the official Cloudflare program:\n{DOWNLOAD_URL}\nSave cloudflared-windows-amd64.exe in the application folder, then start again.')


def stop_process(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def read_lines(process, messages):
    for line in process.stdout:
        messages.put(line.rstrip())
    messages.put(None)


def wait_for_url(process, messages, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            line = messages.get(timeout=0.2)
        except queue.Empty:
            if process.poll() is not None:
                raise ValueError('The tunnel stopped before creating a link. See its error above.')
            continue
        if line is None:
            raise ValueError('The tunnel stopped before creating a link. See its error above.')
        print(line, flush=True)
        match = TUNNEL_URL.search(line)
        if match:
            return match.group(1)
    raise ValueError('No tunnel link received within 60 seconds. Check internet access and try again.')


def main():
    from dotenv import dotenv_values
    if not (ROOT / '.env').is_file():
        raise ValueError('Run install-windows-native.cmd first.')
    executable = find_cloudflared()
    values = dotenv_values(ROOT / '.env')
    if len(values.get('DJANGO_SECRET_KEY') or '') < 32:
        raise ValueError('Set a valid DJANGO_SECRET_KEY in .env before starting.')
    port = int(values.get('APP_PORT') or '8000')
    if not 1 <= port <= 65535:
        raise ValueError('APP_PORT must be between 1 and 65535.')
    # Avoid publishing a different application already listening on this port.
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', port))
    tunnel = server = None
    messages = queue.Queue()
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
    try:
        print('Creating a temporary HTTPS link. Keep this window open.', flush=True)
        tunnel = subprocess.Popen([str(executable), 'tunnel', '--no-autoupdate', '--protocol', 'http2', '--url', f'http://127.0.0.1:{port}'],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', creationflags=flags)
        threading.Thread(target=read_lines, args=(tunnel, messages), daemon=True).start()
        hostname = wait_for_url(tunnel, messages)
        server = subprocess.Popen([sys.executable, str(ROOT/'scripts'/'serve_native.py'), '--no-browser', '--port', str(port), '--public-host', hostname], cwd=ROOT, creationflags=flags)
        deadline = time.monotonic() + 30
        while True:
            if server.poll() is not None or tunnel.poll() is not None:
                raise ValueError('The web server or tunnel stopped. See the error above.')
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=0.3):
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    raise ValueError('Web server did not start within 30 seconds.')
                time.sleep(0.2)
        url = f'https://{hostname}'
        print(f'\nSHARE THIS LINK: {url}\nUsers sign in with their own site accounts.\nThe link may change after restarting. Press Ctrl+C to stop both processes.\n', flush=True)
        webbrowser.open(url)
        while True:
            if server.poll() is not None or tunnel.poll() is not None:
                raise ValueError('The web server or tunnel stopped. Restart this launcher for a new link.')
            try:
                line = messages.get(timeout=0.5)
                if line:
                    print(line, flush=True)
            except queue.Empty:
                pass
    finally:
        stop_process(tunnel)
        stop_process(server)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nInternet access stopped. Database records are preserved.')
    except Exception as error:
        print(f'Internet startup failed: {error}', file=sys.stderr)
        sys.exit(1)
