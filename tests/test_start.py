from dotenv import dotenv_values
import pytest
from start import configure_local


def test_first_run_generates_token_once(tmp_path, monkeypatch):
    monkeypatch.delenv('CODER_BUDDY_TOKEN', raising=False)
    token = configure_local(tmp_path)
    assert len(token) >= 32
    assert dotenv_values(tmp_path / '.env')['CODER_BUDDY_TOKEN'] == token
    assert configure_local(tmp_path) == token


def test_existing_config_preserved(tmp_path, monkeypatch):
    monkeypatch.delenv('CODER_BUDDY_TOKEN', raising=False)
    (tmp_path / '.env').write_text('GROQ_MODEL=my-model\n')
    configure_local(tmp_path)
    assert dotenv_values(tmp_path / '.env')['GROQ_MODEL'] == 'my-model'


def test_invalid_token_requires_explicit_fix(tmp_path, monkeypatch):
    monkeypatch.setenv('CODER_BUDDY_TOKEN', 'short')
    with pytest.raises(ValueError, match='at least 32'):
        configure_local(tmp_path)
    assert not (tmp_path / '.env').exists()
