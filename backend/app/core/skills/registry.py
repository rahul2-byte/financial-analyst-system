"""Bundled, reviewed skill packages for the conversational runtime."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from app.core.prompts import PromptRegistry
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class SkillValidationError(ValueError):
    """A bundled skill is malformed or references files outside its package."""


BUILTIN_TOOL_NAMES = frozenset(
    {
        "data:fetch_stock_data",
        "analysis:get_technical_overview",
        "data:fetch_fundamentals",
        "news:fetch_news",
        "analysis:run_fundamental_scan",
        "analysis:run_technical_scan",
        "interaction:ask_user",
    }
)


class SkillManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    version: str = Field(min_length=1)
    description: str = Field(min_length=1)
    triggers: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    scripts: tuple[str, ...] = ()
    references: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillPackage:
    manifest: SkillManifest
    path: Path
    sha256: str

    def prompt(self, prompts: PromptRegistry | None = None) -> str:
        registry = prompts or PromptRegistry.bundled()
        return registry.get(f"skills.{self.manifest.id.replace('-', '_')}")


class SkillRegistry:
    def __init__(self, skills: dict[str, SkillPackage], prompts: PromptRegistry | None = None) -> None:
        self._skills = dict(sorted(skills.items()))
        self.prompts = prompts or PromptRegistry.bundled()

    @classmethod
    def bundled(cls, root: Path | None = None) -> SkillRegistry:
        package_root = root or Path(__file__).resolve().parents[3] / "skills"
        return cls.load(
            package_root,
            registered_tools=BUILTIN_TOOL_NAMES,
            prompts=PromptRegistry.bundled(),
        )

    @classmethod
    def load(
        cls,
        root: Path,
        *,
        registered_tools: set[str] | frozenset[str] | None = None,
        prompts: PromptRegistry | None = None,
    ) -> SkillRegistry:
        if not root.is_dir():
            raise SkillValidationError(f"skill root does not exist: {root}")
        packages: dict[str, SkillPackage] = {}
        for path in sorted(item for item in root.iterdir() if item.is_dir()):
            skill_file = path / "SKILL.md"
            if not skill_file.is_file():
                continue
            manifest = _read_skill_file(skill_file)
            if manifest.id in packages:
                raise SkillValidationError(f"duplicate skill id: {manifest.id}")
            for relative in (*manifest.scripts, *manifest.references):
                referenced = _safe_child(path, relative)
                if not referenced.is_file():
                    raise SkillValidationError(f"skill file does not exist: {relative}")
            if registered_tools is not None:
                unknown_tools = set(manifest.allowed_tools) - set(registered_tools)
                if unknown_tools:
                    names = ", ".join(sorted(unknown_tools))
                    raise SkillValidationError(
                        f"skill {manifest.id} references unknown tool(s): {names}"
                    )
            digest = hashlib.sha256(skill_file.read_bytes()).hexdigest()
            packages[manifest.id] = SkillPackage(
                manifest=manifest,
                path=path,
                sha256=digest,
            )
        return cls(packages, prompts=prompts)

    def ids(self) -> tuple[str, ...]:
        return tuple(self._skills)

    def get(self, skill_id: str) -> SkillPackage:
        try:
            return self._skills[skill_id]
        except KeyError as exc:
            raise SkillValidationError(f"unknown skill: {skill_id}") from exc

    def select(self, query: str, *, limit: int = 2) -> list[SkillPackage]:
        words = set(re.findall(r"[a-z0-9]+", query.lower()))
        words.update({"analyze"} if "analyse" in words else set())
        ranked: list[tuple[int, str, SkillPackage]] = []
        for skill in self._skills.values():
            triggers = set(" ".join(skill.manifest.triggers).lower().split())
            score = len(words & triggers)
            if score:
                ranked.append((score, skill.manifest.id, skill))
        if not ranked and words & {
            "stock",
            "stocks",
            "company",
            "filing",
            "filings",
            "earnings",
            "market",
            "finance",
            "financial",
        }:
            planning = self._skills.get("equity-research")
            if planning is not None:
                ranked.append((1, planning.manifest.id, planning))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in ranked[:limit]]


def _read_skill_file(path: Path) -> SkillManifest:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise SkillValidationError(f"missing front matter: {path}")
    try:
        _, raw_manifest, _ = text.split("---\n", 2)
        values: dict[str, Any] = yaml.safe_load(raw_manifest) or {}
        return SkillManifest.model_validate(values)
    except (ValueError, TypeError, ValidationError, yaml.YAMLError) as exc:
        raise SkillValidationError(f"invalid manifest: {path}: {exc}") from exc


def _safe_child(package: Path, relative: str) -> Path:
    candidate = (package / relative).resolve()
    try:
        candidate.relative_to(package.resolve())
    except ValueError as exc:
        raise SkillValidationError(
            f"skill path must stay inside the skill package: {relative}"
        ) from exc
    return candidate
