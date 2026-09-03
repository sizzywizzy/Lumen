"""SKILL.md discovery and parsing.

A skill is a folder under the repo's `skills/` directory holding a SKILL.md:
YAML frontmatter (`name`, `description`, a `metadata` map) followed by the
Markdown instructions the agent follows. The body is handed to Gemini verbatim
as the system instruction, so the file *is* the agent's procedure.

Dependency-free on purpose: the frontmatter subset used here (scalars, one
level of nested keys, `[a, b]` lists) is parsed by hand rather than adding
PyYAML for everyone.
"""
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from core import config

SKILL_FILE = "SKILL.md"


class SkillNotFound(KeyError):
    """No SKILL.md for that name under the skills directory."""


@dataclass
class Skill:
    name: str
    description: str
    instructions: str
    metadata: dict[str, Any] = field(default_factory=dict)
    path: Optional[Path] = None
    fingerprint: str = ""

    # -- typed views over metadata -------------------------------------------

    @property
    def agent(self) -> str:
        return str(self.metadata.get("agent") or f"agent_{self.name.replace('-', '_')}")

    @property
    def title(self) -> str:
        """What the dashboard calls this skill, e.g. 'Casting Advisor'."""
        return str(self.metadata.get("title") or self.name.replace("-", " ").title())

    @property
    def cta(self) -> str:
        """The button label: what running the skill does for the user."""
        return str(self.metadata.get("cta") or f"Run {self.title}")

    @property
    def phase(self) -> str:
        return str(self.metadata.get("phase", ""))

    @property
    def model(self) -> str:
        tier = str(self.metadata.get("model", "flash")).lower()
        return "pro" if tier == "pro" else "flash"

    @property
    def owner(self) -> str:
        return str(self.metadata.get("owner", ""))

    @property
    def version(self) -> str:
        return str(self.metadata.get("version", "1"))

    def meta_list(self, key: str) -> list[str]:
        """`markets: US, IN` and `markets: [US, IN]` both read as a list."""
        value = self.metadata.get(key)
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        return [part.strip() for part in str(value).split(",") if part.strip()]

    def meta_int(self, key: str, default: int) -> int:
        try:
            return int(str(self.metadata.get(key, default)).strip())
        except (TypeError, ValueError):
            return default

    def public(self, include_instructions: bool = True) -> dict[str, Any]:
        rel = None
        if self.path:
            try:
                rel = str(self.path.relative_to(config.BACKEND_DIR.parent)).replace("\\", "/")
            except ValueError:
                rel = str(self.path)
        out = {
            "name": self.name,
            "title": self.title,
            "cta": self.cta,
            "description": self.description,
            "agent": self.agent,
            "phase": self.phase,
            "model": self.model,
            "owner": self.owner,
            "version": self.version,
            "metadata": self.metadata,
            "fingerprint": self.fingerprint,
            "path": rel,
        }
        if include_instructions:
            out["instructions"] = self.instructions
        return out


# ------------------------------------------------------------------ parsing --


def _coerce(value: str) -> Any:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        return [_coerce(part) for part in value[1:-1].split(",") if part.strip()]
    return value


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split a SKILL.md into (frontmatter dict, body). No frontmatter -> ({}, text)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text.strip()
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}, text.strip()

    meta: dict[str, Any] = {}
    parent: Optional[str] = None
    for raw in lines[1:end]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        key, sep, value = raw.strip().partition(":")
        if not sep:
            continue
        key = key.strip()
        if indent == 0:
            if value.strip() == "":
                meta[key] = {}
                parent = key
            else:
                meta[key] = _coerce(value)
                parent = None
        elif parent is not None and isinstance(meta.get(parent), dict):
            meta[parent][key] = _coerce(value)
    return meta, "\n".join(lines[end + 1:]).strip()


def _load_file(path: Path) -> Skill:
    text = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)
    name = str(meta.get("name") or path.parent.name).strip()
    metadata = meta.get("metadata") if isinstance(meta.get("metadata"), dict) else {}
    return Skill(
        name=name,
        description=str(meta.get("description", "")).strip(),
        instructions=body,
        metadata=metadata,
        path=path,
        fingerprint=hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
    )


# ---------------------------------------------------------------- discovery --


def skills_dir() -> Path:
    return config.SKILLS_DIR


def load_all() -> list[Skill]:
    """Every skills/*/SKILL.md, sorted by name. Read fresh on each call so an
    edited SKILL.md is used by the next run without a restart."""
    root = skills_dir()
    if not root.exists():
        return []
    skills = [_load_file(p) for p in sorted(root.glob(f"*/{SKILL_FILE}"))]
    return sorted(skills, key=lambda s: s.name)


def get(name: str) -> Skill:
    path = skills_dir() / name / SKILL_FILE
    if path.exists():
        return _load_file(path)
    # The folder name and the frontmatter name may differ; fall back to a scan.
    for skill in load_all():
        if skill.name == name:
            return skill
    raise SkillNotFound(name)
