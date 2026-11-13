"""Local-only launcher with first-run access-token setup."""
import argparse
import os
from pathlib import Path
import secrets
import subprocess
import sys

from dotenv import dotenv_values, set_key

BASE = Path(__file__).resolve().parent


def configure_local(directory: Path) -> str:
    env_file = directory / '.env'
    existing = dotenv_values(env_file) if env_file.exists() else {}
    token = os.getenv('CODER_BUDDY_TOKEN') or existing.get('CODER_BUDDY_TOKEN')
    if token:
        if len(token) < 32:
            raise ValueError('CODER_BUDDY_TOKEN must have at least 32 characters. Fix it in .env.')
        return token
    token = secrets.token_urlsafe(32)
    env_file.touch(mode=0o600, exist_ok=True)
    if os.name != 'nt':
        env_file.chmod(0o600)
    set_key(str(env_file), 'CODER_BUDDY_TOKEN', token)
    return token


def main():
    parser = argparse.ArgumentParser(description='Start Coder Buddy locally; no provider key needed for ChatGPT import')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535')
    try:
        token = configure_local(BASE)
    except (OSError, ValueError) as exc:
        print(f'Setup failed: {exc}', file=sys.stderr)
        return 1
    print(f'Open http://127.0.0.1:{args.port}', flush=True)
    print(f'Local access token (paste into the sign-in form): {token}', flush=True)
    print('Select ChatGPT import to use your ChatGPT account without a Groq API key.', flush=True)
    try:
        return subprocess.call([sys.executable, '-m', 'uvicorn', 'app:app', '--host', '127.0.0.1',
                                '--port', str(args.port), '--workers', '1'], cwd=BASE)
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    sys.exit(main())
