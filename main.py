"""CLI entry point; run uvicorn app:app for the browser application."""
import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4
from dotenv import load_dotenv


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description='Generate a project with Coder Buddy')
    parser.add_argument('--prompt', help='Project description (otherwise prompts interactively)')
    parser.add_argument('--output', type=Path, help='New, empty output directory')
    parser.add_argument('--recursion-limit', '-r', type=int, default=10)
    args = parser.parse_args()
    try:
        from agent.graph import build_agent
        prompt = args.prompt or input('Describe your project: ')
        output = args.output or Path('generated_projects') / uuid4().hex
        if output.exists() and any(output.iterdir()):
            raise ValueError('Output directory must be empty to avoid overwriting existing work')
        result = build_agent(output, progress=lambda stage, text: print(f'[{stage}] {text}')).invoke(
            {'user_prompt': prompt}, {'recursion_limit': args.recursion_limit})
        print(f'Generated {len(result["files"])} files in {output.resolve()}')
        print(json.dumps(result['validation'], indent=2))
    except KeyboardInterrupt:
        print('\nCancelled.', file=sys.stderr)
        return 130
    except Exception as exc:
        print(f'Generation failed ({type(exc).__name__}). Check configuration and server logs.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
