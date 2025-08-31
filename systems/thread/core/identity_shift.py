# systems/thread/core/evaluate_identity_shift_thread.py
#
# REFACTORED FOR THE CENTRALIZED LLM BUS AND SAFE DATABASE LOGGING (3072D-LOCKED)
#
from __future__ import annotations

import json
import re
from typing import Any

# 🔧 Centralized HTTP client + endpoints
from core.utils.net_api import ENDPOINTS, get_http_client

# EcodiaOS Core Imports
from core.utils.time import now, now_iso
from systems.synk.core.tools.neo import add_node
from systems.thread.core.identity_shift_prompts import build_identity_shift_prompt

# 🔢 3072D hard expectation (index + embeddings)
EXPECTED_DIMS = 3072

# ✅ Use our debug-locked embedder (already instrumented)
try:
    from core.llm.embeddings_gemini import get_embedding  # returns list[float]
except Exception:  # pragma: no cover
    get_embedding = None  # type: ignore


def _safe_label(raw: str) -> str:
    """
    Sanitize label for Neo4j (letters, digits, underscore only).
    Example: 'identity:priority' -> 'identity_priority'
    """
    base = (raw or "").strip() or "Unknown"
    return re.sub(r"[^a-zA-Z0-9_]", "_", base)


async def _embed_text_3072(text: str) -> list[float] | None:
    """
    Embed text with a hard expectation of 3072D.
    - Returns the vector (len==3072) or None if not possible.
    - Never raises (so we won't 500 the room).
    """
    if not text or not text.strip():
        print("[IDENTITY LOG] No text to embed; skipping embedding.")
        return None

    if get_embedding is None:
        print("[IDENTITY LOG] Embedding module unavailable; skipping embedding.")
        return None

    try:
        # First attempt: explicit dims + query-appropriate task type
        vec = await get_embedding(text, task_type="RETRIEVAL_DOCUMENT", dimensions=EXPECTED_DIMS)
        if isinstance(vec, list) and len(vec) == EXPECTED_DIMS:
            return vec
        print(
            f"[IDENTITY LOG] Embed len {len(vec) if isinstance(vec, list) else '??'} != {EXPECTED_DIMS}; retrying.",
        )
    except Exception as e:
        print(f"[IDENTITY LOG] First embed attempt failed: {type(e).__name__}: {e}")

    # Retry once, forcing the same parameters (get_embedding itself may reattempt)
    try:
        vec = await get_embedding(text, task_type="RETRIEVAL_DOCUMENT", dimensions=EXPECTED_DIMS)
        if isinstance(vec, list) and len(vec) == EXPECTED_DIMS:
            return vec
        print(
            f"[IDENTITY LOG] Forced embed still not {EXPECTED_DIMS}D; got {len(vec) if isinstance(vec, list) else '??'}.",
        )
    except Exception as e:
        print(f"[IDENTITY LOG] Forced embed failed: {type(e).__name__}: {e}")

    # Give up embedding—callers must handle a None vector gracefully.
    return None


# =========================
# 🧠 Main Entry Point (Refactored)
# =========================
async def evaluate_identity_shift_thread(session: Any, m_event_id: str) -> None:
    """
    Ask the centralized LLM Bus whether an MEvent should be logged as an IdentityState.
    Single, unified call to /llm/call; the bus handles policy, identity, and parsing.
    This version ensures logging never throws due to embedding/index dimensionality.
    """
    print(f"\n🧪 [Thread] Evaluating identity shift for MEvent: {m_event_id}...\n")

    llm_decision: dict[str, Any] | None = None

    try:
        # 1) Build prompt content from business logic
        prompt_data = {
            "event_id": m_event_id,
            "event_data": session.as_dict() if hasattr(session, "as_dict") else {},
            "history": getattr(session, "history", []),
        }
        system_prompt, user_prompt = build_identity_shift_prompt(prompt_data)

        # IMPORTANT: Our centralized formatter ignores 'system' role,
        # so pass everything as a single user message.
        full_user_content = f"{system_prompt}\n\n---\n\n{user_prompt}"

        # 2) Construct standardized request payload for the LLM Bus
        request_payload = {
            "agent_name": "Evo",  # Evo = reflection/identity agent
            "messages": [{"role": "user", "content": full_user_content}],
            "task_context": {
                "scope": "thread_identity_shift_evaluation",
                "purpose": "Evaluate if a recent event signifies a meaningful shift in system identity.",
                "risk": "medium",
                "budget": "normal",
            },
            "provider_overrides": {
                "json_mode": True,  # Require structured output
                "max_tokens": 1024,
                "temperature": 0.2,
            },
        }

        # 3) Call the centralized LLM Bus
        print("🔁 [Thread] Calling central LLM Bus for identity shift evaluation...")
        client = await get_http_client()
        resp = await client.post(ENDPOINTS.LLM_CALL, json=request_payload, timeout=60.0)
        resp.raise_for_status()

        # Bus returns pre-parsed JSON in the 'json' field
        llm_decision = resp.json().get("json")

    except Exception as e:
        print(f"⚠️  [Thread] LLM Bus path failed: {type(e).__name__}: {e}")

    # --- Decision & logging ---

    if not isinstance(llm_decision, dict):
        print("ℹ️ [Thread] No valid JSON decision available from LLM Bus. Skipping log.")
        print("🧠 [Thread] Evaluation complete.\n")
        return

    print(f"📨 [Thread Parsed Response]: {json.dumps(llm_decision, indent=2)}\n")

    try:
        if llm_decision.get("should_log") and llm_decision.get("type"):
            # Sanitize label(s)
            safe_label = _safe_label(str(llm_decision["type"]))
            labels = ["IdentityState", safe_label]

            summary = str(llm_decision.get("summary", "")).strip()
            reason = str(llm_decision.get("reason", "")).strip()

            # 🔐 Pre-embed to 3072D and pass the vector as a property.
            # This avoids any internal utility defaulting to 768D.
            # If embedding fails, we still log the node without vector.
            embed_source_text = summary or reason or f"Identity shift for MEvent {m_event_id}"
            vec = await _embed_text_3072(embed_source_text)

            properties = {
                "summary": summary,
                "reason": reason,
                "state": "active",
                "confidence": llm_decision.get("confidence"),
                "origin_node_id": m_event_id,
                "system": "Thread",
                "created_at": now_iso(),
                "updated_at": now_iso(),
                "timestamp": now(),
            }

            # Only attach vector if we actually have a 3072D one
            if isinstance(vec, list) and len(vec) == EXPECTED_DIMS:
                # Common convention: property named 'embedding'
                properties["embedding"] = vec
                properties["embedding_dims"] = EXPECTED_DIMS
                # We pass embed_text=None to avoid any internal re-embedding with wrong dims
                embed_text_arg: str | None = None
                print(f"[IDENTITY LOG] Attached 3072D embedding to node (len={len(vec)})")
            else:
                embed_text_arg = None  # do not trigger internal embedding
                print("[IDENTITY LOG] Proceeding without embedding (vector unavailable).")

            await add_node(
                labels=labels,
                properties=properties,
                embed_text=embed_text_arg,  # keep None to prevent internal 768D calls
            )
            print(f"✅ [Thread] Identity shift logged for MEvent: {m_event_id}")
        else:
            print("ℹ️ [Thread] No identity shift detected or logged.")
    except Exception as e:
        # Never crash the room from here; surface as soft error.
        print(f"⚠️  [Thread] Logging to graph failed but continuing: {type(e).__name__}: {e}")

    print("🧠 [Thread] Evaluation complete.\n")
