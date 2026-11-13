"""Single-owner web application. Run exactly one server worker per data directory."""
import hmac
import io
import json
import logging
import os
import shutil
import sqlite3
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles

from agent.states import GenerationRequest, ImportRequest, Plan, File
from agent.chatgpt import export_prompt
from agent.tools import Workspace, validate_content, validation_report

logger = logging.getLogger('coder_buddy')
BASE = Path(__file__).resolve().parent


def generate(prompt, root, progress):
    from agent.graph import build_agent
    return build_agent(root, progress=progress).invoke({'user_prompt': prompt})


def create_app(data_dir=None, token=None, runner=None):
    load_dotenv()
    root = Path(data_dir or os.getenv('CODER_BUDDY_DATA_DIR', 'data')).resolve()
    access_token = token if token is not None else os.getenv('CODER_BUDDY_TOKEN', '')
    run = runner or generate
    db_path = root / 'jobs.sqlite3'
    lock = threading.Lock()
    pool = None

    @contextmanager
    def connection():
        conn = sqlite3.connect(db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def update(job_id, **fields):
        with connection() as conn:
            conn.execute('UPDATE jobs SET ' + ', '.join(f'{k}=?' for k in fields) + ' WHERE id=?',
                         (*fields.values(), job_id))

    def get(job_id):
        if len(job_id) != 32 or any(c not in '0123456789abcdef' for c in job_id):
            raise HTTPException(404, 'Project not found')
        with connection() as conn:
            row = conn.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        if row is None:
            raise HTTPException(404, 'Project not found')
        result = dict(row)
        result['result'] = json.loads(result['result']) if result['result'] else None
        return result

    def work(job_id, prompt):
        try:
            update(job_id, status='running', stage='planning', message='Starting generation')
            result = run(prompt, root / 'projects' / job_id,
                         lambda stage, message: update(job_id, stage=stage, message=message))
            if result.get('status') != 'completed' or not result.get('files'):
                raise ValueError('Generation did not complete')
            ws = Workspace(root / 'projects' / job_id)
            for name in result['files']:
                if not ws.read(name).strip():
                    raise ValueError('Missing or empty output')
            payload = {k: result[k] for k in ('files', 'validation')}
            payload['plan'] = result['plan'].model_dump()
            update(job_id, status='completed', stage='completed', message='Files ready for review',
                   result=json.dumps(payload))
        except Exception as exc:
            # Do not log provider responses, credentials, prompts or generated source.
            logger.error('Generation %s failed: %s', job_id, type(exc).__name__)
            update(job_id, status='failed', stage='failed',
                   message='Generation failed. Check the server API key, model access and provider quota, then retry.')

    @asynccontextmanager
    async def lifespan(app):
        nonlocal pool
        if len(access_token) < 32:
            raise RuntimeError('Set CODER_BUDDY_TOKEN to a random secret of at least 32 characters')
        root.mkdir(parents=True, exist_ok=True)
        with connection() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, prompt TEXT NOT NULL, status TEXT NOT NULL,
                stage TEXT NOT NULL, message TEXT NOT NULL, created REAL NOT NULL, result TEXT)''')
            conn.execute("UPDATE jobs SET status='failed', stage='failed', message='Server restarted during generation. Please retry.' WHERE status IN ('queued', 'running')")
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='generation')
        yield
        pool.shutdown(wait=True, cancel_futures=False)

    app = FastAPI(title='Coder Buddy', version='0.2.0', lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # Avoid echoing entire uploaded source files in validation responses.
        messages = ['.'.join(str(p) for p in error['loc'][1:]) + ': ' + error['msg']
                    for error in exc.errors()[:5]]
        return JSONResponse(status_code=422, content={'detail': '; '.join(messages)})

    @app.middleware('http')
    async def security(request: Request, call_next):
        if request.method == 'POST':
            # Read in bounded chunks before JSON parsing, including chunked requests.
            body = bytearray()
            limit = 2000000 if request.url.path == '/api/import' else 40000
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > limit:
                    return Response('Request too large', status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        response.headers['Cache-Control'] = 'no-store'
        return response

    def auth(request: Request):
        supplied = request.headers.get('authorization', '')
        if not hmac.compare_digest(supplied.encode(), ('Bearer ' + access_token).encode()):
            raise HTTPException(401, 'Enter the server access token', headers={'WWW-Authenticate': 'Bearer'})

    @app.get('/healthz')
    def health():
        return {'status': 'ok'}

    @app.get('/')
    def index():
        return FileResponse(BASE / 'web' / 'index.html')

    @app.get('/api/config', dependencies=[Depends(auth)])
    def config():
        return {'provider_configured': runner is not None or bool(os.getenv('GROQ_API_KEY')), 'max_files': 20, 'chatgpt_import': True}

    @app.post('/api/chatgpt-prompt', dependencies=[Depends(auth)])
    def chatgpt_prompt(body: GenerationRequest):
        return {'prompt': export_prompt(body.prompt)}

    @app.post('/api/import', status_code=201, dependencies=[Depends(auth)])
    def import_project(body: ImportRequest):
        # Validate all content before creating a directory or a database row.
        for file in body.project.files:
            try:
                validate_content(file.path, file.content)
            except (ValueError, SyntaxError) as exc:
                raise HTTPException(422, f'{file.path}: invalid or empty content ({type(exc).__name__}). '
                                    'Ask ChatGPT to correct the file and return the full JSON.') from exc
        plan = Plan(name=body.project.name, description=body.project.description,
                    techstack=body.project.techstack, features=['Imported project'],
                    files=[File(path=f.path, purpose='Imported source') for f in body.project.files])
        job_id = uuid4().hex
        folder = root / 'projects' / job_id
        payload = {'files': [f.path for f in body.project.files], 'plan': plan.model_dump(),
                   'validation': validation_report(), 'source': 'chatgpt_import'}
        with lock:
            try:
                with connection() as conn:
                    if conn.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] >= 100:
                        raise HTTPException(409, 'Project limit reached. Delete old projects first.')
                    ws = Workspace(folder)
                    for file in body.project.files:
                        ws.write(file.path, file.content)
                    conn.execute('INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?)',
                                 (job_id, body.prompt, 'completed', 'imported', 'ChatGPT files imported and checked',
                                  time.time(), json.dumps(payload)))
            except Exception:
                if folder.exists():
                    shutil.rmtree(folder)
                raise
        return {'id': job_id, 'status': 'completed'}

    @app.post('/api/projects', status_code=202, dependencies=[Depends(auth)])
    def create_project(body: GenerationRequest):
        if runner is None and not os.getenv('GROQ_API_KEY'):
            raise HTTPException(503, 'GROQ_API_KEY is missing on the server')
        with lock, connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued', 'running')").fetchone()[0]
            if count >= 4:
                raise HTTPException(429, 'Generation queue is full. Try again after a project finishes.')
            if conn.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] >= 100:
                raise HTTPException(409, 'Project limit reached. Delete old projects first.')
            job_id = uuid4().hex
            conn.execute('INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?)',
                         (job_id, body.prompt, 'queued', 'queued', 'Waiting for the worker', time.time(), None))
        pool.submit(work, job_id, body.prompt)
        return {'id': job_id, 'status': 'queued'}

    @app.get('/api/projects', dependencies=[Depends(auth)])
    def projects():
        with connection() as conn:
            rows = conn.execute('SELECT id, prompt, status, stage, message, created FROM jobs ORDER BY created DESC').fetchall()
        return [dict(r) for r in rows]

    @app.get('/api/projects/{job_id}', dependencies=[Depends(auth)])
    def project(job_id: str):
        return get(job_id)

    def completed(job_id):
        job = get(job_id)
        if job['status'] != 'completed':
            raise HTTPException(409, 'Project files are not ready')
        return job

    def read_output(job_id, path):
        try:
            return Workspace(root / 'projects' / job_id).read(path)
        except (OSError, ValueError) as exc:
            raise HTTPException(409, 'Saved file is missing or unavailable. Reimport or regenerate this project.') from exc

    @app.get('/api/projects/{job_id}/file', dependencies=[Depends(auth)])
    def file(job_id: str, path: str):
        job = completed(job_id)
        if path not in job['result']['files']:
            raise HTTPException(404, 'File not found')
        with lock:
            return {'path': path, 'content': read_output(job_id, path)}

    @app.get('/api/projects/{job_id}/download', dependencies=[Depends(auth)])
    def download(job_id: str):
        job = completed(job_id)
        output = io.BytesIO()
        with lock, zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in job['result']['files']:
                archive.writestr(name, read_output(job_id, name))
        return Response(output.getvalue(), media_type='application/zip',
                        headers={'Content-Disposition': f'attachment; filename="coder-buddy-{job_id[:8]}.zip"'})

    @app.delete('/api/projects/{job_id}', status_code=204, dependencies=[Depends(auth)])
    def delete(job_id: str):
        with lock:
            job = get(job_id)
            if job['status'] in ('queued', 'running'):
                raise HTTPException(409, 'Wait for generation to finish before deleting')
            folder = root / 'projects' / job_id
            if folder.exists():
                shutil.rmtree(folder)
            with connection() as conn:
                conn.execute('DELETE FROM jobs WHERE id=?', (job_id,))
        return Response(status_code=204)

    app.mount('/static', StaticFiles(directory=BASE / 'web'), name='static')
    return app


app = create_app()
