"""Filesystem access restricted to an individual generation workspace.

Generated code is never executed on the application host.
"""
import ast
import json
from pathlib import Path
from agent.states import validate_path


class Workspace:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, name: str) -> Path:
        validate_path(name)
        path = self.root / name
        current = path
        while current != self.root:
            if current.is_symlink():
                raise ValueError('Symlinks are not allowed')
            current = current.parent
        if not path.resolve().is_relative_to(self.root):
            raise ValueError('Path escapes workspace')
        return path

    def write(self, name: str, content: str):
        if not content.strip() or len(content.encode('utf-8')) > 400000:
            raise ValueError('File is empty or exceeds 400 KB')
        path = self.path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')

    def read(self, name: str) -> str:
        return self.path(name).read_text(encoding='utf-8')


def validate_content(name: str, content: str):
    """Syntax-only checks. Does not import or execute generated programs."""
    if not content.strip():
        raise ValueError(f'{name}: empty file')
    if content.lstrip().startswith('```'):
        raise ValueError(f'{name}: remove Markdown code fences')
    if name.endswith('.py'):
        ast.parse(content, filename=name)
    elif name.endswith('.json'):
        json.loads(content)


def validation_report():
    return {'file_completeness': 'passed', 'python_json_syntax': 'passed where applicable',
            'runtime_tests': 'not run',
            'notice': 'Generated code is untrusted. Review it and run its tests in an isolated environment.'}
