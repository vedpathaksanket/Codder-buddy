"""Exercise the real container without a provider key. Requires Docker and a built image."""
import io
import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.request
import uuid
import zipfile


def main():
    name = 'coder-buddy-smoke-' + uuid.uuid4().hex[:8]
    volume = name + '-data'
    secret = secrets.token_urlsafe(32)
    environment = dict(os.environ, CODER_BUDDY_TOKEN=secret)
    url = 'http://127.0.0.1:8877'

    def request(path, payload=None, authenticated=True):
        headers = {'Authorization': 'Bearer ' + secret} if authenticated else {}
        data = None
        if payload is not None:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(payload).encode()
        with urllib.request.urlopen(urllib.request.Request(url + path, data=data, headers=headers), timeout=5) as response:
            return response.read()

    def ready():
        for _ in range(60):
            try:
                assert json.loads(request('/healthz', authenticated=False)) == {'status': 'ok'}
                return
            except (OSError, ValueError):
                time.sleep(1)
        raise RuntimeError('Container did not become healthy')

    try:
        subprocess.run(['docker', 'run', '-d', '--name', name, '-p', '127.0.0.1:8877:8000',
                        '--env', 'CODER_BUDDY_TOKEN', '--mount', f'type=volume,source={volume},target=/app/data',
                        'coder-buddy:test'], check=True, env=environment, capture_output=True)
        ready()
        assert subprocess.check_output(['docker', 'exec', name, 'id', '-u'], text=True).strip() == '10001'
        try:
            request('/api/projects', authenticated=False)
            raise AssertionError('Unauthenticated request was allowed')
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        assert not json.loads(request('/api/config'))['provider_configured']
        payload = {'prompt': 'Build a Python greeting application', 'project': {
            'name': 'Greeting', 'description': 'Print a greeting', 'techstack': 'Python',
            'files': [{'path': 'main.py', 'content': "print('Hello')"},
                      {'path': 'README.md', 'content': 'Run python main.py'}]}}
        job = json.loads(request('/api/import', payload))
        with zipfile.ZipFile(io.BytesIO(request(f'/api/projects/{job["id"]}/download'))) as archive:
            assert archive.read('main.py') == b"print('Hello')"
        subprocess.run(['docker', 'restart', name], check=True, capture_output=True)
        ready()
        assert json.loads(request('/api/projects'))[0]['id'] == job['id']
        print('PASS: non-root image, startup, authentication, no-key import, ZIP and restart persistence')
    finally:
        subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
        subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True)


if __name__ == '__main__':
    main()
