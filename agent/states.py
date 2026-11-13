"""Validated contracts shared by the three generation stages."""
import re
from pathlib import PurePosixPath
from pydantic import BaseModel, ConfigDict, Field, field_validator


def validate_path(value: str) -> str:
    if not value or len(value) > 240 or '\\' in value or ':' in value:
        raise ValueError('Use a relative POSIX file path')
    parts = value.split('/')
    if any(p in ('', '.', '..') or p.startswith('.') for p in parts):
        raise ValueError('Hidden files, empty segments and traversal are not allowed')
    if PurePosixPath(value).is_absolute() or not re.fullmatch(r'[A-Za-z0-9_./ -]+', value):
        raise ValueError('Unsafe file path')
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class File(StrictModel):
    path: str
    purpose: str = Field(min_length=1, max_length=2000)
    _path = field_validator('path')(validate_path)


class Plan(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=4000)
    techstack: str = Field(min_length=1, max_length=1000)
    features: list[str] = Field(min_length=1, max_length=30)
    files: list[File] = Field(min_length=1, max_length=20)

    @field_validator('files')
    @classmethod
    def unique_files(cls, files):
        paths = [f.path.casefold() for f in files]
        if len(paths) != len(set(paths)):
            raise ValueError('Duplicate file paths')
        return files


class ImplementationTask(StrictModel):
    filepath: str
    task_description: str = Field(min_length=1, max_length=6000)
    _path = field_validator('filepath')(validate_path)


class TaskPlan(StrictModel):
    implementation_steps: list[ImplementationTask] = Field(min_length=1, max_length=20)


class GeneratedFile(StrictModel):
    content: str = Field(min_length=1, max_length=100000)


class GenerationRequest(StrictModel):
    prompt: str = Field(min_length=10, max_length=8000)

    @field_validator('prompt')
    @classmethod
    def trim_prompt(cls, value):
        value = value.strip()
        if len(value) < 10:
            raise ValueError('Describe your project in at least 10 characters')
        return value
