import pytest
from pydantic import ValidationError

from agent.graph import GenerationError, build_agent
from agent.states import File, GeneratedFile, Plan, TaskPlan, ImplementationTask
from agent.tools import Workspace, validate_content


def plan():
    return Plan(name='Hello', description='A runnable Python greeting', techstack='Python',
                features=['Greeting'], files=[File(path='main.py', purpose='Entry point'),
                                            File(path='README.md', purpose='Run instructions')])


class FakeModel:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.prompts = []

    def with_structured_output(self, schema, **kwargs):
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result


def architecture():
    return TaskPlan(implementation_steps=[ImplementationTask(filepath=f.path, task_description=f.purpose)
                                          for f in plan().files])


def test_full_pipeline_and_context(tmp_path):
    model = FakeModel([plan(), architecture(), GeneratedFile(content="print('Hello')\n"),
                       GeneratedFile(content='# Hello\nRun python main.py\n')])
    stages = []
    result = build_agent(tmp_path, model, lambda stage, msg: stages.append(stage)).invoke(
        {'user_prompt': 'Create a Python greeting application'})
    assert result['status'] == 'completed'
    assert result['files'] == ['main.py', 'README.md']
    assert (tmp_path / 'main.py').read_text() == "print('Hello')\n"
    assert "print('Hello')" in model.prompts[-1]
    assert result['validation']['runtime_tests'] == 'not run'
    assert stages == ['planning', 'architecting', 'coding', 'coding', 'validating']


def test_invalid_syntax_is_repaired_once(tmp_path):
    model = FakeModel([plan(), architecture(), GeneratedFile(content='def broken('),
                       GeneratedFile(content="print('fixed')"), GeneratedFile(content='Run python main.py')])
    result = build_agent(tmp_path, model).invoke({'user_prompt': 'Create a Python greeting application'})
    assert result['status'] == 'completed'
    assert 'Previous output failed validation' in model.prompts[3]


def test_repeated_invalid_output_never_succeeds(tmp_path):
    model = FakeModel([plan(), architecture(), GeneratedFile(content='def broken('),
                       GeneratedFile(content='def broken(')])
    with pytest.raises(GenerationError):
        build_agent(tmp_path, model).invoke({'user_prompt': 'Create a Python greeting application'})
    assert not (tmp_path / 'main.py').exists()


def test_missing_plan_file_is_rejected(tmp_path):
    tasks = TaskPlan(implementation_steps=[ImplementationTask(filepath='other.py', task_description='Bad')])
    with pytest.raises(GenerationError):
        build_agent(tmp_path, FakeModel([plan(), tasks])).invoke({'user_prompt': 'Create a test application'})


@pytest.mark.parametrize('path', ['../secret', '/etc/passwd', 'C:/secret', 'a\\b', '.env', 'a/../b',
                                 'a//b', 'a/.git/config', '.', 'file\x00.txt'])
def test_unsafe_paths_rejected(tmp_path, path):
    with pytest.raises(ValueError):
        Workspace(tmp_path).write(path, 'bad')


def test_symlink_escape(tmp_path):
    root = tmp_path / 'root'
    ws = Workspace(root)
    (root / 'link').symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        ws.write('link/out.txt', 'bad')


def test_duplicate_paths_rejected():
    data = plan().model_dump()
    data['files'].append({'path': 'MAIN.py', 'purpose': 'Duplicate'})
    with pytest.raises(ValidationError):
        Plan.model_validate(data)


def test_syntax_checks_do_not_execute(tmp_path):
    content = f"from pathlib import Path\nPath({str(tmp_path / 'marker')!r}).touch()"
    validate_content('main.py', content)
    assert not (tmp_path / 'marker').exists()
    with pytest.raises(ValueError):
        validate_content('package.json', '{bad}')


def test_import_does_not_require_key(monkeypatch, tmp_path):
    monkeypatch.delenv('GROQ_API_KEY', raising=False)
    with pytest.raises(GenerationError, match='GROQ_API_KEY'):
        build_agent(tmp_path)
