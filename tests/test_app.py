import io
import threading
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from app import create_app
from agent.states import File, Plan
from agent.tools import Workspace

TOKEN = 'test-only-' + 'x' * 32
HEADERS = {'Authorization': f'Bearer {TOKEN}'}


def runner(prompt, root, progress):
    progress('coding', 'Writing main.py')
    ws = Workspace(root)
    ws.write('main.py', "print('Hello')\n")
    ws.write('README.md', '# Hello\nRun python main.py')
    return {'status': 'completed', 'files': ['main.py', 'README.md'],
            'plan': Plan(name='Hello', description='Greeting', techstack='Python', features=['Greeting'],
                         files=[File(path='main.py', purpose='Entry'), File(path='README.md', purpose='Guide')]),
            'validation': {'runtime_tests': 'not run'}}


def wait(client, job_id):
    for _ in range(200):
        job = client.get(f'/api/projects/{job_id}', headers=HEADERS).json()
        if job['status'] not in ('queued', 'running'):
            return job
        time.sleep(.01)
    pytest.fail('Job did not finish')


def test_full_api_lifecycle_and_persistence(tmp_path):
    with TestClient(create_app(tmp_path, TOKEN, runner)) as client:
        assert client.get('/').status_code == 200
        assert client.get('/healthz').json() == {'status': 'ok'}
        assert client.get('/api/projects').status_code == 401
        assert client.get('/api/projects', headers={'Authorization': 'Bearer wrong'}).status_code == 401
        assert client.post('/api/projects', headers=HEADERS, json={'prompt': 'short'}).status_code == 422
        response = client.post('/api/projects', headers=HEADERS, json={'prompt': 'Create a Python greeting app'})
        assert response.status_code == 202
        job_id = response.json()['id']
        job = wait(client, job_id)
        assert job['status'] == 'completed'
        assert job['result']['validation']['runtime_tests'] == 'not run'
        response = client.get(f'/api/projects/{job_id}/file', params={'path': 'main.py'}, headers=HEADERS)
        assert response.json()['content'] == "print('Hello')\n"
        assert client.get(f'/api/projects/{job_id}/file', params={'path': '../jobs.sqlite3'}, headers=HEADERS).status_code == 404
        archive = client.get(f'/api/projects/{job_id}/download', headers=HEADERS)
        with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
            assert z.namelist() == ['main.py', 'README.md']
        assert "frame-ancestors 'none'" in response.headers['content-security-policy']
    with TestClient(create_app(tmp_path, TOKEN, runner)) as client:
        assert len(client.get('/api/projects', headers=HEADERS).json()) == 1
        assert client.delete(f'/api/projects/{job_id}', headers=HEADERS).status_code == 204
        assert client.get(f'/api/projects/{job_id}', headers=HEADERS).status_code == 404
        assert not (tmp_path / 'projects' / job_id).exists()


def test_missing_provider_and_token(tmp_path, monkeypatch):
    monkeypatch.delenv('GROQ_API_KEY', raising=False)
    with TestClient(create_app(tmp_path, TOKEN)) as client:
        assert client.post('/api/projects', headers=HEADERS, json={'prompt': 'Build a useful app'}).status_code == 503
    with pytest.raises(RuntimeError, match='CODER_BUDDY_TOKEN'):
        with TestClient(create_app(tmp_path, 'short', runner)):
            pass


def test_error_redaction(tmp_path):
    def broken(*args):
        raise RuntimeError('secret-provider-key')
    with TestClient(create_app(tmp_path, TOKEN, broken)) as client:
        job_id = client.post('/api/projects', headers=HEADERS, json={'prompt': 'Build a useful app'}).json()['id']
        job = wait(client, job_id)
        assert job['status'] == 'failed'
        assert 'secret-provider-key' not in str(job)
        assert client.get(f'/api/projects/{job_id}/download', headers=HEADERS).status_code == 409


def test_bounded_queue_and_running_delete(tmp_path):
    release = threading.Event()
    def slow(*args):
        release.wait(5)
        return runner(*args)
    with TestClient(create_app(tmp_path, TOKEN, slow)) as client:
        try:
            ids = [client.post('/api/projects', headers=HEADERS, json={'prompt': 'Build a useful app'}).json()['id'] for _ in range(4)]
            assert client.post('/api/projects', headers=HEADERS, json={'prompt': 'Build a useful app'}).status_code == 429
            assert client.delete(f'/api/projects/{ids[0]}', headers=HEADERS).status_code == 409
        finally:
            release.set()
        for job_id in ids:
            assert wait(client, job_id)['status'] == 'completed'
        assert len(list((tmp_path / 'projects').iterdir())) == 4


def test_request_size_and_missing_project(tmp_path):
    with TestClient(create_app(tmp_path, TOKEN, runner)) as client:
        assert client.post('/api/projects', headers=HEADERS, content='x' * 40001).status_code == 413
        assert client.get('/api/projects/not-an-id', headers=HEADERS).status_code == 404
