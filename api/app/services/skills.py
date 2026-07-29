"""Skill loader — a skill's ``SKILL.md`` becomes the Claude system prompt.

Ported from QAgent's ``services/skills.py``, reduced to the one skill the hub
runs. ADR 0007 lets the hub build **hub-owned data**; it does not let the hub do
an agent's job, so there is no test-generation, review or execution skill here
and adding one is a decision, not a copy.

A skill lives at ``<settings.skills_path>/<name>/SKILL.md`` with optional
``templates/*``. The prompt the caller writes still pins the JSON shape the
backend parses; the skill supplies the methodology.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import settings
from app.logging import logger

#: The only skill the hub runs (ADR 0007).
PROJECT_BOOTSTRAP = "project-bootstrap"

SKILLS = frozenset({PROJECT_BOOTSTRAP})

__all__ = ["PROJECT_BOOTSTRAP", "SKILLS", "load_skill"]


@lru_cache(maxsize=8)
def _read_skill(root: str, name: str, include_template: bool) -> str | None:
    from pathlib import Path

    skill_dir = Path(root) / name
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        logger.warning("Skill '%s' not found at %s — proceeding without it", name, skill_md)
        return None

    parts = [
        (
            "You are operating under the dedicated EMESOFT skill below. Follow "
            "its workflow, coverage rules and quality rules precisely.\n"
        ),
        skill_md.read_text(encoding="utf-8"),
    ]
    if include_template:
        template_dir = skill_dir / "templates"
        if template_dir.is_dir():
            for template in sorted(template_dir.glob("*")):
                if template.is_file():
                    parts.append(f"\n--- Reference template: {template.name} ---\n")
                    parts.append(template.read_text(encoding="utf-8"))
    return "\n".join(parts)


def load_skill(name: str, include_template: bool = False) -> str | None:
    """The composed skill text, or ``None`` when the skill is not on disk.

    A missing skill is a warning, not a failure: a build without the skill still
    produces a usable knowledge base, just a less opinionated one. The cache is
    keyed on the resolved root as well as the name so the test suite can point
    ``skills_dir`` somewhere else without a stale hit.
    """
    if name not in SKILLS:
        raise ValueError(f"Unknown skill '{name}'")
    return _read_skill(str(settings.skills_path), name, include_template)
