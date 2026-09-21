from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from string import Formatter
from typing import Any

import yaml


class PromptConfigurationError(ValueError):
    """Prompt configuration is unreadable or violates the prompt schema."""


class PromptNotFoundError(PromptConfigurationError):
    """A required semantic prompt key is not registered."""


class PromptRenderError(PromptConfigurationError):
    """A registered prompt cannot be rendered with the supplied variables."""


class _UniqueLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: _UniqueLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise PromptConfigurationError(f"duplicate YAML key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


class PromptRegistry:
    def __init__(self, prompts: Mapping[str, str], source: Path) -> None:
        self._prompts = dict(prompts)
        self.source = source

    @classmethod
    @lru_cache(maxsize=1)
    def bundled(cls) -> PromptRegistry:
        return cls.load(Path(__file__).with_name("prompts.yaml"))

    @classmethod
    def load(cls, path: Path) -> PromptRegistry:
        try:
            with path.open("r", encoding="utf-8") as handle:
                raw = yaml.load(handle, Loader=_UniqueLoader)
        except FileNotFoundError as exc:
            raise PromptConfigurationError(f"prompt file does not exist: {path}") from exc
        except (OSError, UnicodeError, yaml.YAMLError, PromptConfigurationError) as exc:
            raise PromptConfigurationError(f"invalid prompt file {path}: {exc}") from exc
        if not isinstance(raw, dict) or set(raw) != {"prompts"}:
            raise PromptConfigurationError("prompt YAML must contain only a prompts mapping")
        flattened: dict[str, str] = {}
        _flatten(raw["prompts"], (), flattened)
        if not flattened:
            raise PromptConfigurationError("prompt YAML contains no prompts")
        return cls(flattened, path)

    def get(self, key: str) -> str:
        try:
            return self._prompts[key]
        except KeyError as exc:
            raise PromptNotFoundError(
                f"required prompt '{key}' was not found in {self.source}"
            ) from exc

    def render(self, key: str, **variables: str) -> str:
        template = self.get(key)
        expected = _placeholders(template, key)
        supplied = set(variables)
        missing = expected - supplied
        unexpected = supplied - expected
        if missing:
            raise PromptRenderError(
                f"prompt '{key}' missing variable(s): {', '.join(sorted(missing))}"
            )
        if unexpected:
            raise PromptRenderError(
                f"prompt '{key}' has unexpected variable(s): {', '.join(sorted(unexpected))}"
            )
        try:
            return template.format_map(variables)
        except (KeyError, ValueError, IndexError) as exc:
            raise PromptRenderError(f"prompt '{key}' could not be rendered: {exc}") from exc

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._prompts))


def _flatten(value: Any, path: tuple[str, ...], output: dict[str, str]) -> None:
    if not isinstance(value, dict):
        raise PromptConfigurationError(
            f"prompt namespace '{'.'.join(path) or '<root>'}' must be a mapping"
        )
    for name, child in value.items():
        if not isinstance(name, str) or not name or "." in name:
            raise PromptConfigurationError("prompt namespace names must be non-empty and dot-free")
        current = (*path, name)
        if isinstance(child, dict) and set(child) == {"template"}:
            template = child["template"]
            if not isinstance(template, str) or not template.strip():
                raise PromptConfigurationError(f"prompt '{'.'.join(current)}' must have a non-empty template")
            _placeholders(template, ".".join(current))
            output[".".join(current)] = template
        elif isinstance(child, dict):
            _flatten(child, current, output)
        else:
            raise PromptConfigurationError(f"prompt namespace '{'.'.join(current)}' is invalid")


def _placeholders(template: str, key: str) -> set[str]:
    names: set[str] = set()
    try:
        parts = Formatter().parse(template)
        for _, field_name, format_spec, conversion in parts:
            if field_name is None:
                continue
            if not field_name.isidentifier() or format_spec or conversion:
                raise PromptConfigurationError(
                    f"prompt '{key}' contains an invalid placeholder: {{{field_name}}}"
                )
            names.add(field_name)
    except (ValueError, TypeError) as exc:
        raise PromptConfigurationError(f"prompt '{key}' has malformed placeholders: {exc}") from exc
    return names
