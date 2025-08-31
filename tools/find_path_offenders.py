import re
from pathlib import Path

root = Path("/app")
patterns = [
    re.compile(r'["\']/app/EcodiaOS[^"\']*["\']'),
    re.compile(r'["\']EcodiaOS[^"\']*["\']'),
]
for p in root.rglob("*.py"):
    if any(seg in (".git", "__pycache__") for seg in p.parts):
        continue
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    hits = []
    for pat in patterns:
        for m in pat.finditer(text):
            hits.append((m.start(), m.group(0)))
    if hits:
        print(f"\n== {p} ==")
        for _, s in hits[:25]:
            print(" ", s)
