"""Bundled, reviewed skill packages for the conversational runtime."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class SkillValidationError(ValueError):
    """A bundled skill is malformed or references files outside its package."""


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
    instructions: str
    sha256: str

    def prompt(self) -> str:
        return (
            f"Active FIN-AI skill: {self.manifest.id} v{self.manifest.version}\n"
            f"Skill contract: {self.manifest.description}\n"
            "Use only verified evidence. Keep calculations and quantitative claims "
            "grounded in deterministic tool outputs; do not invent missing data.\n\n"
            f"{self.instructions.strip()}"
        )


class SkillRegistry:
    def __init__(self, skills: dict[str, SkillPackage]) -> None:
        self._skills = dict(sorted(skills.items()))

    @classmethod
    def bundled(cls, root: Path | None = None) -> SkillRegistry:
        package_root = root or Path(__file__).resolve().parents[3] / "skills"
        return cls.load(package_root)

    @classmethod
    def load(cls, root: Path) -> SkillRegistry:
        if not root.is_dir():
            raise SkillValidationError(f"skill root does not exist: {root}")
        packages: dict[str, SkillPackage] = {}
        for path in sorted(item for item in root.iterdir() if item.is_dir()):
            skill_file = path / "SKILL.md"
            if not skill_file.is_file():
                continue
            manifest, instructions = _read_skill_file(skill_file)
            if manifest.id in packages:
                raise SkillValidationError(f"duplicate skill id: {manifest.id}")
            for relative in (*manifest.scripts, *manifest.references):
                referenced = _safe_child(path, relative)
                if not referenced.is_file():
                    raise SkillValidationError(f"skill file does not exist: {relative}")
            digest = hashlib.sha256(skill_file.read_bytes()).hexdigest()
            packages[manifest.id] = SkillPackage(
                manifest=manifest,
                path=path,
                instructions=instructions,
                sha256=digest,
            )
        return cls(packages)

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
            planning = self._skills.get("research-planning")
            if planning is not None:
                ranked.append((1, planning.manifest.id, planning))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in ranked[:limit]]


def _read_skill_file(path: Path) -> tuple[SkillManifest, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise SkillValidationError(f"missing front matter: {path}")
    try:
        _, raw_manifest, instructions = text.split("---\n", 2)
        values: dict[str, Any] = yaml.safe_load(raw_manifest) or {}
        return SkillManifest.model_validate(values), instructions
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
