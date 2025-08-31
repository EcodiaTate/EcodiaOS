# ===== FILE: systems/simula/agent/tool_specs_additions.py =====
"""
Nuke #2: Tool Registry & Adapter Consolidation

CHANGES:
- Removed duplicate definitions for `qora_recipe_write` and `qora_recipe_find`.
  These were already specified in the Qora-provided tool catalog, causing redundancy.
- This cleanup ensures a single, authoritative definition for each tool.
"""

ADDITIONAL_TOOL_SPECS = [
    {
        "name": "open_pr",
        "description": "Create a branch, apply the diff, commit, and open a PR (best-effort; may be dry-run in sandbox).",
        "parameters": {
            "type": "object",
            "properties": {
                "diff": {"type": "string"},
                "title": {"type": "string"},
                "evidence": {"type": "object"},
                "base": {"type": "string"},
            },
            "required": ["diff", "title"],
        },
        "returns": {"type": "object"},
    },
    {
        "name": "package_artifacts",
        "description": "Bundle evidence + reports into a tar.gz with manifest for reviewers.",
        "parameters": {
            "type": "object",
            "properties": {
                "proposal_id": {"type": "string"},
                "evidence": {"type": "object"},
                "extra_paths": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["proposal_id", "evidence"],
        },
        "returns": {"type": "object"},
    },
    {
        "name": "qora_pr_macro",
        "description": "Apply a diff, create a branch, commit, push, and open a PR (via gh if present) in one shot.",
        "parameters": {
            "type": "object",
            "properties": {
                "diff": {"type": "string"},
                "branch_base": {"type": "string", "default": "main"},
                "branch_name": {"type": ["string", "null"]},
                "commit_message": {"type": "string", "default": "Apply Simula/Qora proposal"},
                "remote": {"type": "string", "default": "origin"},
                "pr_title": {"type": "string", "default": "Simula/Qora proposal"},
                "pr_body_markdown": {"type": "string", "default": ""},
            },
            "required": ["diff"],
        },
        "returns": {"type": "object"},
        "safety": 2,
    },
    {
        "name": "write_code",
        "description": "Directly write or overwrite the full content of a file at a given path. Use this when you have a complete implementation ready.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The repository-relative path to the file to write.",
                },
                "content": {
                    "type": "string",
                    "description": "The full source code or text to write into the file.",
                },
            },
            "required": ["path", "content"],
        },
        "returns": {"type": "object"},
        "safety": 2,
    },
    {
        "name": "policy_gate",
        "description": "Run EOS policy packs against a diff and return findings.",
        "parameters": {
            "type": "object",
            "properties": {"diff": {"type": "string"}},
            "required": ["diff"],
        },
        "returns": {"type": "object"},
    },
    {
        "name": "impact_and_cov",
        "description": "Compute impact (changed files, -k expression) and delta coverage summary for a diff.",
        "parameters": {
            "type": "object",
            "properties": {"diff": {"type": "string"}},
            "required": ["diff"],
        },
        "returns": {"type": "object"},
    },
    {
        "name": "render_ci_yaml",
        "description": "Render a minimal CI pipeline (GitHub/GitLab) that runs hygiene/test gates.",
        "parameters": {
            "type": "object",
            "properties": {
                "provider": {"type": "string"},
                "use_xdist": {"type": ["boolean", "integer"]},
            },
        },
        "returns": {"type": "object"},
    },
    {
        "name": "conventional_commit_title",
        "description": "Generate a conventional-commit title string based on evidence.",
        "parameters": {
            "type": "object",
            "properties": {"evidence": {"type": "object"}},
            "required": ["evidence"],
        },
        "returns": {"type": "object"},
    },
    {
        "name": "conventional_commit_message",
        "description": "Render a complete conventional commit message.",
        "parameters": {
            "type": "object",
            "properties": {
                "type": {"type": "string"},
                "scope": {"type": ["string", "null"]},
                "subject": {"type": "string"},
                "body": {"type": ["string", "null"]},
            },
            "required": ["type", "subject"],
        },
        "returns": {"type": "object"},
    },
    {
        "name": "format_patch",
        "description": "Auto-format changed files across languages (ruff/black/isort, prettier, gofmt, rustfmt).",
        "parameters": {
            "type": "object",
            "properties": {"paths": {"type": "array", "items": {"type": "string"}}},
            "required": ["paths"],
        },
        "returns": {"type": "object"},
    },
    {
        "name": "rebase_patch",
        "description": "Attempt to apply a unified diff on top of a base branch (3-way), reporting conflicts if any.",
        "parameters": {
            "type": "object",
            "properties": {"diff": {"type": "string"}, "base": {"type": "string"}},
            "required": ["diff"],
        },
        "returns": {"type": "object"},
    },
    {
        "name": "local_select_patch",
        "description": "Locally score and rank candidate diffs when Synapse selection is unavailable.",
        "parameters": {
            "type": "object",
            "properties": {
                "candidates": {"type": "array", "items": {"type": "object"}},
                "top_k": {"type": "integer"},
            },
            "required": ["candidates"],
        },
        "returns": {"type": "object"},
    },
    {
        "name": "record_recipe",
        "description": "Persist a runbook recipe for a solved task (SoC long-term memory).",
        "parameters": {
            "type": "object",
            "properties": {
                "goal": {"type": "string"},
                "context_fqname": {"type": "string"},
                "steps": {"type": "array", "items": {"type": "string"}},
                "success": {"type": "boolean"},
                "impact_hint": {"type": "string"},
            },
            "required": ["goal", "context_fqname", "steps", "success"],
        },
        "returns": {"type": "object"},
    },
    {
        "name": "run_ci_locally",
        "description": "Run project-native build/tests locally (supports python/node/go/java/rust/bazel/cmake).",
        "parameters": {
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"}},
                "timeout_sec": {"type": "integer"},
            },
        },
        "returns": {"type": "object"},
    },
]
