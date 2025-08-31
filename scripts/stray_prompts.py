# dev/find_stray_prompts.py
import re
from pathlib import Path

ROOTS = [Path("core"), Path("systems"), Path("api")]

PATTERNS = {
    "direct_llm_bus": re.compile(r"post\([^)]*?/llm/call", re.IGNORECASE),
    "messages_list": re.compile(
        r"\[\s*{\s*['\"]role['\"]\s*:\s*['\"](system|user|assistant)['\"]",
        re.MULTILINE,
    ),
    "jinja_usage": re.compile(r"jinja2\.(Environment|Template)", re.IGNORECASE),
    "respond_only_json": re.compile(
        r"Respond\s+ONLY\s+with\s+a\s+single\s+JSON\s+object",
        re.IGNORECASE,
    ),
    "templates_yaml_key": re.compile(
        r"[\"'](simula_react_step|evo_question_generation|atune_next_step_planning|analysis_symbolism|analysis_contradiction|voxis_query_generation|thread_identity_shift_analysis|unity_deliberation_turn|unity_judge_decision|unity_synthesis|genesis_tool_specification)[\"']",
    ),
}


def scan_file(p: Path):
    try:
        txt = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    hits = []
    for name, rx in PATTERNS.items():
        if rx.search(txt):
            hits.append(name)
    return hits


def main():
    for root in ROOTS:
        for p in root.rglob("*.py"):
            hits = scan_file(p)
            if hits:
                print(f"{p}: {', '.join(hits)}")


if __name__ == "__main__":
    main()
