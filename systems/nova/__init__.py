# file: systems/nova/__init__.py
"""
Nova package (lightweight init).

Important:
- Do NOT import submodules here (runners, ledger, schemas, clients).
- Always import explicitly from submodules, e.g.:
    from systems.nova.schemas import InnovationBrief
    from systems.nova.runners.playbook_runner import PlaybookRunner

Rationale:
- Prevent circular imports with Evo (e.g., EvoEngine -> NovaClient -> nova.runners.*),
  since importing any submodule first initialises this package. Keeping this file
  empty of cross-imports avoids cycles and speeds startup.
"""

from __future__ import annotations

__version__ = "0.1-mvp"

__all__ = ["__version__"]
