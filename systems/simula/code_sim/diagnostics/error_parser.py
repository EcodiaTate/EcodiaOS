# systems/simula/code_sim/diagnostics/error_parser.py
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Failure:
    file: str
    line: int
    test: str | None
    errtype: str | None
    message: str | None


_TEST_LINE = re.compile(r"^(.+?):(\d+): (?:in )?(.+)$")
_FAIL_HEADER = re.compile(r"^=+ FAILURES =+$|^_+ (.+?) _+$")
_ERR_TYPE = re.compile(r"^E\s+([A-Za-z_][A-Za-z0-9_\.]*):\s*(.*)$")
_STACK_PATH = re.compile(r"^(.+?):(\d+): in (.+)$")


def parse_pytest_output(stdout: str) -> list[Failure]:
    """
    Extract failing test locations from pytest output. Robust to -q and verbose formats.
    """
    if not stdout:
        return []
    lines = stdout.splitlines()
    failures: list[Failure] = []
    cur_test: str | None = None
    cur_errtype: str | None = None
    cur_msg: str | None = None
    cur_file: str | None = None
    cur_line: int | None = None

    def _flush():
        nonlocal cur_test, cur_errtype, cur_msg, cur_file, cur_line
        if cur_file and cur_line:
            failures.append(Failure(cur_file, int(cur_line), cur_test, cur_errtype, cur_msg))
        cur_test = cur_errtype = cur_msg = cur_file = None
        cur_line = None

    for i, ln in enumerate(lines):
        if _FAIL_HEADER.match(ln):
            _flush()
            cur_test = None
            continue
        m = _STACK_PATH.match(ln)
        if m:
            cur_file, cur_line, _fn = m.group(1), int(m.group(2)), m.group(3)
            continue
        m = _TEST_LINE.match(ln)
        if m and not cur_file:
            cur_file, cur_line, cur_test = m.group(1), int(m.group(2)), m.group(3)
            continue
        m = _ERR_TYPE.match(ln)
        if m:
            cur_errtype, cur_msg = m.group(1), m.group(2)
            # flush at the end of a block or if next failure begins
            _flush()
    _flush()
    # Deduplicate by (file,line)
    seen = set()
    uniq: list[Failure] = []
    for f in failures:
        key = (f.file, f.line)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(f)
    return uniq
