"""
Versioned prompt template loader for simulation agents.

Usage:
    from modules.simulation.prompts import prompt_loader

    # Get a raw template string (with $variable placeholders)
    template = prompt_loader.load("persona", section="BEHAVIOR_BLOCK")

    # Render a template with variables substituted
    text = prompt_loader.render("persona", section="BEHAVIOR_BLOCK", persona_name="Alice")

    # List available versions
    versions = prompt_loader.list_versions("persona")
"""

import os
import re
from string import Template
from typing import Dict, Optional, List


# Map short agent names to file name stems
_AGENT_FILE_MAP = {
    "persona": "persona_system",
    "grading": "grading_system",
    "summarization": "summarization_system",
}

_PROMPTS_DIR = os.path.dirname(os.path.abspath(__file__))


class PromptLoader:
    """Load, cache, and render versioned prompt templates.

    Template files live alongside this module and use ``$variable`` syntax
    (Python ``string.Template``).  Each file may contain multiple named
    sections delimited by ``## SECTION_NAME`` headers.  Call
    ``load(agent, section=...)`` to retrieve a specific section, or omit
    *section* to get the entire file.
    """

    def __init__(self):
        # {(agent_type, version): raw_file_content}
        self._file_cache: Dict[tuple, str] = {}
        # {(agent_type, version): {section_name: section_text}}
        self._section_cache: Dict[tuple, Dict[str, str]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(
        self,
        agent_type: str,
        version: str = "v1",
        section: Optional[str] = None,
    ) -> str:
        """Return the raw template string (un-rendered) for *agent_type*.

        Parameters
        ----------
        agent_type : str
            One of ``"persona"``, ``"grading"``, ``"summarization"``.
        version : str
            Template version tag, e.g. ``"v1"``.  Falls back to ``"v1"``
            if the requested version file does not exist.
        section : str, optional
            If provided, return only the named ``## SECTION`` block.
            If ``None``, the full file contents are returned.
        """
        raw = self._load_file(agent_type, version)
        if section is None:
            return raw
        sections = self._parse_sections(agent_type, version)
        return sections.get(section, "")

    def render(
        self,
        agent_type: str,
        version: str = "v1",
        section: Optional[str] = None,
        **variables,
    ) -> str:
        """Render a template with the given *variables* substituted.

        Uses ``string.Template.safe_substitute`` so that any un-provided
        placeholders are left as-is rather than raising an error.
        """
        raw = self.load(agent_type, version=version, section=section)
        return Template(raw).safe_substitute(variables)

    def list_versions(self, agent_type: str) -> List[str]:
        """Return sorted list of available version tags for *agent_type*."""
        stem = _AGENT_FILE_MAP.get(agent_type, agent_type)
        versions = []
        for fname in os.listdir(_PROMPTS_DIR):
            if fname.startswith(stem + "_") and fname.endswith(".txt"):
                # e.g. "persona_system_v1.txt" -> "v1"
                tag = fname[len(stem) + 1 : -4]  # strip stem_ prefix and .txt suffix
                versions.append(tag)
        return sorted(versions)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_path(self, agent_type: str, version: str) -> str:
        stem = _AGENT_FILE_MAP.get(agent_type, agent_type)
        path = os.path.join(_PROMPTS_DIR, f"{stem}_{version}.txt")
        if not os.path.isfile(path) and version != "v1":
            # Fallback to v1
            path = os.path.join(_PROMPTS_DIR, f"{stem}_v1.txt")
        return path

    def _load_file(self, agent_type: str, version: str) -> str:
        key = (agent_type, version)
        if key not in self._file_cache:
            path = self._resolve_path(agent_type, version)
            with open(path, "r", encoding="utf-8") as f:
                self._file_cache[key] = f.read()
        return self._file_cache[key]

    def _parse_sections(self, agent_type: str, version: str) -> Dict[str, str]:
        key = (agent_type, version)
        if key not in self._section_cache:
            raw = self._load_file(agent_type, version)
            sections: Dict[str, str] = {}
            current_name: Optional[str] = None
            current_lines: list = []

            for line in raw.splitlines():
                match = re.match(r"^## (\S+)\s*$", line)
                if match:
                    if current_name is not None:
                        sections[current_name] = "\n".join(current_lines).strip()
                    current_name = match.group(1)
                    current_lines = []
                else:
                    current_lines.append(line)

            # Flush last section
            if current_name is not None:
                sections[current_name] = "\n".join(current_lines).strip()

            self._section_cache[key] = sections
        return self._section_cache[key]


# Module-level singleton
prompt_loader = PromptLoader()

__all__ = ["prompt_loader", "PromptLoader"]
