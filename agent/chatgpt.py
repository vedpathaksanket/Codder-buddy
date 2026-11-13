"""Manual ChatGPT bridge. No account credentials or automatic subscription calls."""
import json
from agent.states import ProjectBundle


def export_prompt(brief: str) -> str:
    return f'''Build a complete small project for this brief:
{brief}

Return ONLY one valid JSON object matching the schema below, with no Markdown fences
or text outside JSON. Put the full source of every file in its content string, with
JSON-escaped newlines and quotes. Include README.md with truthful setup, run and test
instructions. Maximum 20 files, 100000 characters per file, 1 MB combined file contents.
Use relative POSIX filenames portable to Windows. No hidden files, traversal, secrets,
symlinks or reserved names (CON, NUL, etc.). Do not include placeholder implementations.
Choose a minimal stack. Ensure imports, paths and interfaces agree between files.
Do not claim tests passed unless you actually executed them.
If the scope is too large, deliver a smaller working implementation and explain its
limitations in README.md. Do not truncate JSON or omit file contents.
Schema:
{json.dumps(ProjectBundle.model_json_schema())}
'''
