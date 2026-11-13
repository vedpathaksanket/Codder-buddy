import copy
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app import create_app
from tests.test_app import TOKEN, HEADERS


def bundle():
    return {'prompt': 'Build a Python greeting program', 'project': {
        'name': 'Greeting', 'description': 'Print a greeting', 'techstack': 'Python',
        'files': [{'path': 'main.py', 'content': "print('Hello, Sanket!')\n"},
                  {'path': 'README.md', 'content': 'Run python main.py'}]}}


def test_import_without_provider_roundtrip(tmp_path, monkeypatch):
    monkeypatch.delenv('GROQ_API_KEY', raising=False)
    with TestClient(create_app(tmp_path, TOKEN)) as client:
        assert not client.get('/api/config', headers=HEADERS).json()['provider_configured']
        prompt = client.post('/api/chatgpt-prompt', headers=HEADERS,
                             json={'prompt': bundle()['prompt']}).json()['prompt']
        assert 'Build a Python greeting program' in prompt
        assert 'README.md' in prompt
        assert TOKEN not in prompt
        assert client.post('/api/import', json=bundle()).status_code == 401
        result = client.post('/api/import', headers=HEADERS, json=bundle())
        assert result.status_code == 201
        job_id = result.json()['id']
        job = client.get(f'/api/projects/{job_id}', headers=HEADERS).json()
        assert job['stage'] == 'imported'
        assert job['result']['source'] == 'chatgpt_import'
        assert job['result']['validation']['runtime_tests'] == 'not run'
        response = client.get(f'/api/projects/{job_id}/download', headers=HEADERS)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert archive.read('main.py').decode() == "print('Hello, Sanket!')\n"
        (tmp_path / 'projects' / job_id / 'main.py').unlink()
        assert client.get(f'/api/projects/{job_id}/download', headers=HEADERS).status_code == 409
        assert client.get(f'/api/projects/{job_id}/file', params={'path': 'main.py'}, headers=HEADERS).status_code == 409


@pytest.mark.parametrize('change', ['syntax', 'traversal', 'duplicate', 'collision', 'readme', 'empty', 'large', 'reserved'])
def test_invalid_import_is_atomic(tmp_path, change):
    data = copy.deepcopy(bundle())
    files = data['project']['files']
    if change == 'syntax':
        files[0]['content'] = 'def broken('
    elif change == 'traversal':
        files[0]['path'] = '../outside.py'
    elif change == 'duplicate':
        files.append({'path': 'MAIN.py', 'content': 'pass'})
    elif change == 'collision':
        files.append({'path': 'main.py/child.py', 'content': 'pass'})
    elif change == 'readme':
        files.pop()
    elif change == 'empty':
        files[0]['content'] = ' '
    elif change == 'large':
        files[0]['content'] = 'x' * 100001
    elif change == 'reserved':
        files[0]['path'] = 'CON.py'
    with TestClient(create_app(tmp_path, TOKEN)) as client:
        response = client.post('/api/import', headers=HEADERS, json=data)
        assert response.status_code == 422
        assert client.get('/api/projects', headers=HEADERS).json() == []
        assert not (tmp_path / 'projects').exists()
        assert files[0]['content'] not in response.text if len(files[0]['content']) > 100 else True


def test_import_never_executes_source(tmp_path):
    data = bundle()
    marker = tmp_path / 'executed'
    data['project']['files'][0]['content'] = f"from pathlib import Path\nPath({str(marker)!r}).touch()"
    with TestClient(create_app(tmp_path, TOKEN)) as client:
        assert client.post('/api/import', headers=HEADERS, json=data).status_code == 201
    assert not marker.exists()


def test_large_import_request_rejected(tmp_path):
    with TestClient(create_app(tmp_path, TOKEN)) as client:
        assert client.post('/api/import', headers=HEADERS, content='x' * 2000001).status_code == 413
