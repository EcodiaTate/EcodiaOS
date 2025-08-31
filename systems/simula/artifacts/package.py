# systems/simula/artifacts/package.py
from __future__ import annotations

import hashlib
import json
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ArtifactBundle:
    path: str
    manifest_path: str
    sha256: str


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _collect(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        pp = Path(p)
        if pp.is_file():
            out.append(pp)
        elif pp.is_dir():
            for q in pp.rglob("*"):
                if q.is_file():
                    out.append(q)
    return out


def create_artifact_bundle(
    *,
    proposal_id: str,
    evidence: dict[str, object],
    extra_paths: list[str] | None = None,
) -> ArtifactBundle:
    ts = int(time.time())
    root = Path("artifacts/bundles")
    root.mkdir(parents=True, exist_ok=True)
    tar_path = root / f"{proposal_id}_{ts}.tar.gz"
    manifest = {
        "proposal_id": proposal_id,
        "ts": ts,
        "evidence": evidence,
        "extra": extra_paths or [],
    }
    manifest_path = root / f"{proposal_id}_{ts}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(manifest_path, arcname=manifest_path.name)
        for p in _collect(["artifacts/reports"] + (extra_paths or [])):
            try:
                tar.add(p, arcname=str(p))
            except Exception:
                pass

    return ArtifactBundle(
        path=str(tar_path),
        manifest_path=str(manifest_path),
        sha256=_sha256(tar_path),
    )
