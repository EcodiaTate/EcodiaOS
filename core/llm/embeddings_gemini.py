# core/llm/embeddings_gemini.py
"""
EcodiaOS Embeddings (Gemini) — Equor-aligned defaults via Neo4j (DEBUG BUILD)
- Local-first .env (D:\\EcodiaOS\\config\\.env), ENV_FILE override, then find_dotenv()
- Defaults pulled from Neo4j config node if present; cached with TTL
- Async-safe (thread offload for SDK), retries, batch embeddings
- HARD-LOCKED to 3072 dims + loud runtime assertions + debug prints/sanity probe
"""
from __future__ import annotations
import httpx, os
import asyncio
import json
import os
import time
from collections.abc import Sequence
from typing import Any

from core.llm.env_bootstrap import *  # ensure GOOGLE_API_KEY etc. loaded

try:
    import numpy as np  # optional
except Exception:
    np = None  # type: ignore

from dotenv import find_dotenv, load_dotenv

# ─────────────────────────────────────────────
# Debug toggles
# ─────────────────────────────────────────────
def _is_debug() -> int:
    v = os.getenv("EMBED_DEBUG", "1").strip()
    try:
        return int(v)
    except Exception:
        return 1

def _dbg_print(lvl: int, *args, **kwargs) -> None:
    if _is_debug() >= lvl:
        print(*args, **kwargs)

def _truncate(s: str, n: int = 1400) -> str:
    return s if len(s) <= n else s[:n] + f"... <+{len(s) - n} chars>"

# ─────────────────────────────────────────────
# Env loading (local dev hard-prefer)
# ─────────────────────────────────────────────
LOCAL_ENV_PATH = r"D:\EcodiaOS\config\.env"
if os.path.exists(LOCAL_ENV_PATH):
    load_dotenv(dotenv_path=LOCAL_ENV_PATH)
else:
    env_file = os.getenv("ENV_FILE")
    if env_file and os.path.exists(env_file):
        load_dotenv(dotenv_path=env_file)
    else:
        found = find_dotenv()
        if found:
            load_dotenv(dotenv_path=found)

# ─────────────────────────────────────────────
# Google GenAI client
# ─────────────────────────────────────────────
API_KEY = (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
if not API_KEY:
    raise OSError("No API key set. Define GOOGLE_API_KEY or GEMINI_API_KEY.")

from google import genai
_CLIENT = genai.Client()  # reads GOOGLE_API_KEY

ENV_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "").strip()
DEFAULT_MODEL_FALLBACK = "gemini-embedding-001"

# HARD LOCK to 3072 (Gemini supports this for text)
MIN_DIMS, MAX_DIMS = 3072, 3072
VALID_TASK_TYPES = {"RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY", "SEMANTIC_SIMILARITY", "CLASSIFICATION", "CLUSTERING"}

# ─────────────────────────────────────────────
# Neo4j-backed Equor defaults (cached)
# ─────────────────────────────────────────────
try:
    from core.utils.neo.cypher_query import cypher_query  # async
    _HAS_DB = True
except Exception:
    cypher_query = None  # type: ignore
    _HAS_DB = False

_DEFAULTS_CACHE: dict[str, Any] = {}
_DEFAULTS_LOCK = asyncio.Lock()
_DEFAULTS_TTL_SEC = int(os.getenv("EMBED_DEFAULTS_TTL_SEC", "600"))
_DEFAULTS_LAST_LOAD = 0.0

def _normalize_model(name: str) -> str:
    n = (name or "").strip()
    return n[7:] if n.startswith("models/") else n


async def _load_defaults_from_neo() -> dict[str, Any]:
    if not (_HAS_DB and cypher_query):
        return {}
    queries = [
        "MATCH (c:Config {key:'embedding_defaults'}) RETURN c.model AS model, c.task_type AS task_type, c.dimensions AS dimensions LIMIT 1",
        "MATCH (c:EquorConfig {kind:'embedding'}) RETURN c.model AS model, c.task_type AS task_type, c.dimensions AS dimensions LIMIT 1",
        "MATCH (c:EmbeddingDefaults) RETURN c.model AS model, c.task_type AS task_type, c.dimensions AS dimensions LIMIT 1",
    ]
    for q in queries:
        try:
            rows = await cypher_query(q, {})
            if rows:
                rec = rows[0]
                out: dict[str, Any] = {}
                if rec.get("model"): out["model"] = str(rec["model"]).strip()
                if rec.get("task_type"): out["task_type"] = str(rec["task_type"]).strip().upper()
                if rec.get("dimensions") is not None: out["dimensions"] = int(rec["dimensions"])
                if out: return out
        except Exception as e:
            _dbg_print(2, f"[EMBED DEBUG] _load_defaults_from_neo soft-fail: {e}")
            continue
    return {}

def _validate_dims(dimensions: int) -> int:
    try:
        d = int(dimensions)
    except Exception:
        raise ValueError(f"dimensions must be an integer in [{MIN_DIMS}, {MAX_DIMS}]")
    if not (MIN_DIMS <= d <= MAX_DIMS):
        raise ValueError(f"dimensions must be in [{MIN_DIMS}, {MAX_DIMS}], got {d}")
    return d

async def _get_defaults(now: float | None = None) -> tuple[str, str, int]:
    global _DEFAULTS_LAST_LOAD
    ts = now or time.time()
    if _DEFAULTS_CACHE and (ts - _DEFAULTS_LAST_LOAD) < _DEFAULTS_TTL_SEC:
        return (_DEFAULTS_CACHE["model"], _DEFAULTS_CACHE["task_type"], _DEFAULTS_CACHE["dimensions"])
    async with _DEFAULTS_LOCK:
        if _DEFAULTS_CACHE and (ts - _DEFAULTS_LAST_LOAD) < _DEFAULTS_TTL_SEC:
            return (_DEFAULTS_CACHE["model"], _DEFAULTS_CACHE["task_type"], _DEFAULTS_CACHE["dimensions"])
        neo = await _load_defaults_from_neo()
        model = _normalize_model( (neo.get("model") or ENV_MODEL or DEFAULT_MODEL_FALLBACK).strip() )
        task_type = ((neo.get("task_type") or os.getenv("EMBED_TASK_TYPE", "RETRIEVAL_DOCUMENT")).strip().upper())
        try:
            raw_dims = int(neo.get("dimensions") if "dimensions" in neo else os.getenv("EMBED_DIMENSIONS", MAX_DIMS))
        except Exception:
            raw_dims = MAX_DIMS
        if task_type not in VALID_TASK_TYPES:
            task_type = "RETRIEVAL_DOCUMENT"
        dimensions = _validate_dims(raw_dims)
        _DEFAULTS_CACHE.update({"model": model, "task_type": task_type, "dimensions": dimensions})
        _DEFAULTS_LAST_LOAD = ts
        _dbg_print(1, f"[EMBED DEFAULTS] model={model} task={task_type} dims={dimensions}")
        return model, task_type, dimensions

# 1) Put this near your other helpers
# core/llm/embeddings_gemini.py  — replace your REST helpers

def _rest_embed_single(model: str, contents: str, task_type: str, dimensions: int):
    import httpx, os
    api_key = (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"
    body = {
        "model": f"models/{model}",  # <- include model in body
        "content": {"parts": [{"text": contents}]},
        "taskType": task_type,
        "outputDimensionality": dimensions,
    }
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,   # <- put key in header (not query string)
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, headers=headers, json=body)
        if resp.status_code != 200:
            _dbg_print(1, f"[EMBED REST ERROR] {resp.status_code} {_truncate(resp.text, 1200)}")
            resp.raise_for_status()
        return resp.json()

def _rest_batch_embed(model: str, texts: list[str], task_type: str, dimensions: int) -> dict[str, Any]:
    import httpx, os
    api_key = (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents"
    body = {
        "model": f"models/{model}",  # <- include model in body
        "requests": [
            {
                "content": {"parts": [{"text": t}]},
                "taskType": task_type,
                "outputDimensionality": dimensions,
            } for t in texts
        ]
    }
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,   # <- header
    }
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, headers=headers, json=body)
        if resp.status_code != 200:
            _dbg_print(1, f"[EMBED REST ERROR/BATCH] {resp.status_code} {_truncate(resp.text, 1200)}")
            resp.raise_for_status()
        return resp.json()



# ─────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────
def _ensure_list(vec: Any, name: str = "embedding") -> list[float]:
    if isinstance(vec, list):
        return [float(x) for x in vec]
    if np is not None and isinstance(vec, np.ndarray):  # type: ignore
        return vec.astype(float).tolist()
    if isinstance(vec, str):
        try:
            return [float(x) for x in json.loads(vec)]
        except Exception as e:
            raise TypeError(f"[ERROR] {name} string cannot be parsed: {e}")
    raise TypeError(f"[ERROR] {name} invalid type: {type(vec)}")

def _validate_text(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Input text must be a non-empty string.")
    return text.strip()

def _extract_single_values(res: Any) -> list[float]:
    """Normalize SDK or REST responses to list[float]."""
    # SDK shapes
    try:
        return [float(x) for x in res.embedding.values]  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        return [float(x) for x in res.embeddings[0].values]  # type: ignore[attr-defined]
    except Exception:
        pass
    # REST dict shapes
    if isinstance(res, dict):
        emb = res.get("embedding")
        if isinstance(emb, dict) and "values" in emb:
            return [float(x) for x in emb["values"]]
        embs = res.get("embeddings")
        if isinstance(embs, list) and embs:
            first = embs[0]
            if isinstance(first, dict):
                if "values" in first: return [float(x) for x in first["values"]]
                if "embedding" in first: return [float(x) for x in first["embedding"]]
    raise TypeError(f"Unrecognized embedding response shape: {type(res)}")

def _embed_sync_call(*, model: str, contents: str, task_type: str, dimensions: int):
    """
    Version-agnostic SDK call with guaranteed REST fallback.
    If EMBED_FORCE_REST is set, go REST immediately (no exceptions).
    """
    _dbg_print(2, f"[EMBED CALL] model={model} task={task_type} dims={dimensions} text={_truncate(contents, 200)}")

    # Force REST: DO NOT raise; just call REST and return the JSON
    if os.getenv("EMBED_FORCE_REST", "").strip().lower() in ("1", "true", "yes"):
        return _rest_embed_single(model, contents, task_type, dimensions)

    try:
        return _CLIENT.models.embed_content(
            model=model,
            contents=contents,
            task_type=task_type,
            output_dimensionality=dimensions,
        )
    except TypeError as e_old:
        _dbg_print(1, f"[EMBED WARN] SDK(old) form failed: {e_old}")
    except Exception as e_other:
        _dbg_print(1, f"[EMBED WARN] SDK error: {e_other}")

    # SDK path B: newer SDK expects 'content='
    try:
        return _CLIENT.models.embed_content(
            model=model,
            content=contents,
            task_type=task_type,
            output_dimensionality=dimensions,
        )
    except Exception as e_new:
        _dbg_print(1, f"[EMBED WARN] SDK(new) form failed; using REST: {e_new}")

    # REST fallback
    return _rest_embed_single(model, contents, task_type, dimensions)

def _rest_batch_embed(model: str, texts: list[str], task_type: str, dimensions: int) -> dict[str, Any]:
    import httpx
    api_key = os.environ["GOOGLE_API_KEY"].strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents?key={api_key}"
    body = {
        "requests": [
            {
                "content": {"parts": [{"text": t}]},
                "taskType": task_type,
                "outputDimensionality": dimensions,
            }
            for t in texts
        ]
    }
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, json=body)
        resp.raise_for_status()
        return resp.json()

async def _retry(coro_factory, *, retries: int = 3, base_delay: float = 0.5, jitter: float = 0.25):
    attempt = 0
    last_err = None
    while attempt <= retries:
        try:
            return await coro_factory()
        except Exception as e:
            last_err = e
            if attempt == retries:
                break
            delay = base_delay * (2**attempt) + (jitter if (attempt % 2 == 0) else jitter * 0.5)
            _dbg_print(1, f"[EMBED RETRY] attempt={attempt + 1}/{retries} delay={delay:.2f}s err={e}")
            await asyncio.sleep(delay)
            attempt += 1
    assert last_err is not None
    raise last_err

# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────
async def get_embedding(
    text: str,
    *,
    task_type: str | None = None,
    dimensions: int | None = None,
    model: str | None = None,
) -> list[float]:
    contents = _validate_text(text)
    def_model, def_task, def_dims = await _get_defaults()

    chosen_model = (model or def_model).strip()
    chosen_task = (task_type or def_task or "RETRIEVAL_DOCUMENT").strip().upper()
    if chosen_task not in VALID_TASK_TYPES:
        _dbg_print(1, f"[EMBED WARN] Invalid task_type='{chosen_task}', forcing RETRIEVAL_DOCUMENT")
        chosen_task = "RETRIEVAL_DOCUMENT"

    req_dims = int(dimensions) if dimensions is not None else def_dims
    chosen_dims = _validate_dims(req_dims)

    def _sync():
        return _embed_sync_call(
            model=chosen_model,
            contents=contents,
            task_type=chosen_task,
            dimensions=chosen_dims,
        )

    result = await _retry(lambda: asyncio.to_thread(_sync))
    emb = _extract_single_values(result)

    if len(emb) != chosen_dims or chosen_dims != 3072:
        raise RuntimeError(f"[EMBED ERROR] Expected 3072 dims, got {len(emb)} (requested {chosen_dims})")

    vec = _ensure_list(emb, name="embedding")
    _dbg_print(2, f"[EMBED OK] len={len(vec)} task={chosen_task} model={chosen_model}")
    return vec

async def get_embeddings(
    texts: Sequence[str],
    *,
    task_type: str | None = None,
    dimensions: int | None = None,
    model: str | None = None,
    concurrency: int = 4,
) -> list[list[float]]:
    if not isinstance(texts, (list, tuple)) or not texts:
        raise ValueError("texts must be a non-empty sequence of strings.")

    def_model, def_task, def_dims = await _get_defaults()
    chosen_model = (model or def_model).strip()
    chosen_task = (task_type or def_task or "RETRIEVAL_DOCUMENT").strip().upper()
    if chosen_task not in VALID_TASK_TYPES:
        _dbg_print(1, f"[EMBED WARN] Invalid task_type='{chosen_task}', forcing RETRIEVAL_DOCUMENT")
        chosen_task = "RETRIEVAL_DOCUMENT"
    req_dims = int(dimensions) if dimensions is not None else def_dims
    chosen_dims = _validate_dims(req_dims)

    use_batch = os.getenv("EMBED_USE_REST_BATCH", "1").lower() not in ("0", "false", "no")
    force_rest = os.getenv("EMBED_FORCE_REST", "").strip().lower() in ("1","true","yes")
    if (use_batch or force_rest) and len(texts) > 1:
        data = _rest_batch_embed(chosen_model, list(texts), chosen_task, chosen_dims)
        embs = data.get("embeddings") or []
        if not isinstance(embs, list) or len(embs) != len(texts):
            raise RuntimeError(f"Batch embeddings mismatch: expected {len(texts)}, got {len(embs)}")
        out: list[list[float]] = []
        for i, e in enumerate(embs):
            vec = _ensure_list(e.get("values") or e.get("embedding") or [], name=f"embedding[{i}]")
            if len(vec) != chosen_dims or chosen_dims != 3072:
                raise RuntimeError(f"[EMBED ERROR] Expected 3072 dims, got {len(vec)} at idx={i}")
            _dbg_print(2, f"[EMBED OK/BATCH] idx={i} len={len(vec)}")
            out.append(vec)
        return out

    # Per-item path (SDK/REST with retries)
    sem = asyncio.Semaphore(max(1, int(concurrency)))
    out: list[list[float] | None] = [None] * len(texts)

    async def _one(i: int, t: str):
        txt = _validate_text(t)
        async with sem:
            def _sync():
                return _embed_sync_call(
                    model=chosen_model,
                    contents=txt,
                    task_type=chosen_task,
                    dimensions=chosen_dims,
                )
            res = await _retry(lambda: asyncio.to_thread(_sync))
            vec = _ensure_list(_extract_single_values(res), name=f"embedding[{i}]")
            if len(vec) != chosen_dims or chosen_dims != 3072:
                raise RuntimeError(f"[EMBED ERROR] Expected 3072 dims, got {len(vec)} (requested {chosen_dims}) at idx={i}")
            out[i] = vec
            _dbg_print(2, f"[EMBED OK/BATCH] idx={i} len={len(vec)}")

    await asyncio.gather(*[asyncio.create_task(_one(i, s)) for i, s in enumerate(texts)])
    return [v if v is not None else [] for v in out]

# ─────────────────────────────────────────────
# Optional sanity probe (call once at app startup)
# ─────────────────────────────────────────────
async def _embed_sanity_probe() -> None:
    model, task, dims = await _get_defaults()
    try:
        v = await get_embedding("sanity check: synapse metacognitive kernel phase II")
        print(f"[EMBED SANITY] model={model} task={task} dims(default)={dims} len(vec)={len(v)} OK")
    except Exception as e:
        print(f"[EMBED SANITY] FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(_embed_sanity_probe())
