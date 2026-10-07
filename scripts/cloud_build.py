"""Build with the cloud's existing proxy and public CA trust, without baking them in."""
import os
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

root = Path(__file__).resolve().parent.parent
os.environ.setdefault('DOCKER_CONFIG', '/tmp/autoparts-docker')
Path(os.environ['DOCKER_CONFIG']).mkdir(parents=True, exist_ok=True)
command = ['docker', 'build', '--network=host', '-t', 'autoparts-web:local']
hosts = set()
for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY']:
    if os.environ.get(key):
        command.extend(['--build-arg', key])
        if key != 'NO_PROXY':
            host = urlsplit(os.environ[key]).hostname
            if host and host not in hosts:
                command.extend(['--add-host', f'{host}:{socket.gethostbyname(host)}'])
                hosts.add(host)
certificate = Path(os.environ.get('SSL_CERT_FILE', '/etc/ssl/certs/ca-certificates.crt'))
if certificate.is_file():
    command.extend(['--secret', f'id=cloud_ca,src={certificate}'])
command.append('.')
raise SystemExit(subprocess.call(command, cwd=root))
