"""Test-only server with a deterministic generator; never use for deployment."""
import tempfile
import uvicorn
from app import create_app
from tests.test_app import TOKEN, runner

if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as directory:
        uvicorn.run(create_app(directory, TOKEN, runner), host='127.0.0.1', port=8765)
