# systems/voxis/core/voxis_pipeline.py
# FINAL, COMPLETE VERSION — God Plan (with Tool Use Capability)

from __future__ import annotations

import json
import re
import sys
import traceback
from typing import Any, Dict
from uuid import uuid4

# --- EcodiaOS Core & System Imports ---
from core.utils.net_api import ENDPOINTS, get_http_client
from core.utils.time import now_iso
# Corrected import path for user profile service
from core.utils.user_profile_services import get_user_profile
from systems.synk.core.tools.neo import add_node, add_relationship

# --- PROMPT ORCHESTRATOR ---
from core.prompting.orchestrator import PolicyHint, build_prompt

# --- REAL, PRODUCTION CLIENTS ---
from core.services.synapse import synapse
from core.services.equor import equor
from core.services.ember import ember
from core.services.qora import qora
from systems.synapse.schemas import TaskContext, Candidate

def log(*args, **kwargs):
    print("[VOXIS PIPELINE]", *args, **kwargs, file=sys.stderr, flush=True)

class VoxisPipeline:
    def __init__(self, user_input: str, user_id: str, phrase_event_id: str, output_mode: str = "voice"):
        log(f"INIT: user_id={user_id!r}, phrase_event_id={phrase_event_id!r}, mode={output_mode!r}")
        self.user_input = user_input
        self.user_id = user_id
        self.phrase_event_id = phrase_event_id
        self.output_mode = output_mode
        self.episode_id = None
        self.champion_arm_id = None

    def _build_atune_event(self, final_response: str) -> dict[str, Any]:
        """
        Shapes the conversational turn into a canonical AxonEvent expected by Atune.
        """
        return {
            "event_id": str(uuid4()),
            "event_type": "voxis.output.review.requested",
            "source": "EcodiaOS.Voxis",
            "parsed": {
                "text_blocks": [
                    f"USER_INPUT: {self.user_input}",
                    f"VOXIS_CANDIDATE_RESPONSE: {final_response}",
                ],
                "meta": {
                    "user_id": self.user_id,
                    "phrase_event_id": self.phrase_event_id,
                    "episode_id": self.episode_id,
                    "tactic_used": self.champion_arm_id,
                    "created_at": now_iso(),
                },
            },
        }

    async def _post_to_atune_route(self, axon_event: dict[str, Any]) -> dict[str, Any]:
        """
        POSTs the event to Atune for salience, reflex, and conformal analysis.
        """
        try:
            client = await get_http_client()
            decision_id = f"voxis-turn-{self.episode_id or uuid4().hex}"
            resp = await client.post(
                ENDPOINTS.ATUNE_ROUTE,
                json=axon_event,
                headers={"x-budget-ms": "800", "x-decision-id": decision_id},
            )
            resp.raise_for_status()
            log(f"ATUNE_ROUTE OK: decision_id={decision_id}")
            return resp.json() or {}
        except Exception as e:
            log(f"ATUNE_ROUTE ERROR: {e}")
            return {"status": "error", "error": str(e)}
            
    async def run(self) -> Dict[str, Any]:
        try:
            log("==== START PIPELINE (AGENT) ====")
            client = await get_http_client()

            # --- Stage 1: Deep Context Gathering ---
            user_profile = await get_user_profile(self.phrase_event_id)

            # --- Stage 2: Assembling the Ecodia Mind ---
            compose_response = await equor.compose(agent="ecodia", profile_name="prod")
            constitutional_preamble = compose_response.text
            
            task_ctx = TaskContext(task_key="voxis.conversation.strategy", goal="Select conversational tactic", risk_level="low", budget="normal")
            candidates = [
                Candidate(id="tactic.empathetic.v1", content={}),
                Candidate(id="tactic.challenging.v1", content={}),
                Candidate(id="tactic.storytelling.v1", content={})
            ]
            selection = await synapse.select_arm(task_ctx=task_ctx, candidates=candidates)
            self.champion_arm_id = selection.champion_arm.arm_id
            self.episode_id = selection.episode_id
            
            affect = await ember.get_affect(
                task_context={
                    "task_key": task_ctx.task_key,
                    "goal": task_ctx.goal,
                    "user_input": self.user_input
                }
            )
            current_mood = affect['mood']
            log(f"Ember predicts consequential mood: {current_mood}")

            # --- Stage 3: Generate Initial Response (Pass 1) ---
            log("Building initial prompt via Orchestrator...")
            tactic_instruction = {
                "tactic.empathetic.v1": "Your tactic is EMPATHY...",
                "tactic.challenging.v1": "Your tactic is CHALLENGE...",
                "tactic.storytelling.v1": "Your tactic is STORYTELLING...",
            }.get(self.champion_arm_id, "Your tactic is to respond naturally.")

            context_dict = {
                "preamble": constitutional_preamble,
                "tactic_instruction": tactic_instruction,
                "mood": current_mood,
                "user_profile": user_profile,
                "user_input": self.user_input
            }
            hint = PolicyHint(scope="voxis.expressive_generation.v1", context=context_dict)
            prompt_data = await build_prompt(hint)

            llm_payload = {
                "agent_name": "Voxis.Performer",
                "messages": prompt_data.messages,
                "provider_overrides": prompt_data.provider_overrides,
            }
            resp_llm = await client.post(ENDPOINTS.LLM_CALL, json=llm_payload)
            resp_llm.raise_for_status()
            initial_response = (resp_llm.json().get("text") or "").strip()
            log(f"Raw LLM response (pass 1): {initial_response!r}")
            
            # --- NEW: Stage 3.5: Tool Use Detection and Execution ---
            tool_match = re.search(r"\[tool:\s*(.*?)\]", initial_response)
            
            if tool_match:
                tool_query = tool_match.group(1).strip()
                log(f"Tool call detected. Query: '{tool_query}'")
                try:
                    tool_result = await qora.execute_by_query(query=tool_query)
                    log(f"Tool result: {tool_result}")
                    
                    # Second LLM Pass to synthesize the tool result into a natural response
                    tool_context = {
                        "tool_query": tool_query,
                        "tool_result_json": json.dumps(tool_result.get("result", "No result returned.")),
                        "original_user_input": self.user_input
                    }
                    hint_2 = PolicyHint(scope="voxis.tool_result_synthesis.v1", context=tool_context)
                    prompt_data_2 = await build_prompt(hint_2)
                    
                    llm_payload_2 = {
                        "agent_name": "Voxis.Synthesizer",
                        "messages": prompt_data_2.messages,
                        "provider_overrides": prompt_data_2.provider_overrides,
                    }
                    resp_llm_2 = await client.post(ENDPOINTS.LLM_CALL, json=llm_payload_2)
                    resp_llm_2.raise_for_status()
                    expressive_text = (resp_llm_2.json().get("text") or "").strip()
                    log(f"Final synthesized response (pass 2): {expressive_text!r}")

                except Exception as e:
                    log(f"Tool execution or synthesis failed: {e}")
                    expressive_text = "[softly] I tried to perform an action, but encountered an error."
            else:
                expressive_text = initial_response

            # --- Stage 4 & 5: Persist, Log Outcome, and Route to Atune ---
            await self._log_exchange(expressive_text)
            
            # Create a more detailed initial metrics payload
            initial_metrics = {
                "chosen_arm_id": self.champion_arm_id,
                "utility": 0.5, # Start with a neutral utility before user feedback
                "response_length": len(expressive_text),
                "tool_used": bool(tool_match),
                "tool_query": tool_query if tool_match else None,
            }
            
            await synapse.log_outcome(
                episode_id=self.episode_id,
                task_key=task_ctx.task_key,
                metrics=initial_metrics
            )
            log(f"Logged initial outcome for episode {self.episode_id} to Synapse.")
            
            atune_event = self._build_atune_event(expressive_text)
            atune_result = await self._post_to_atune_route(atune_event)
            
            # --- Stage 6: Final Response Packaging ---
            final_response = {
                "mode": self.output_mode,
                "expressive_text": expressive_text,
                "arm_id": self.champion_arm_id,
                "episode_id": self.episode_id,
                "atune_decision_id": atune_result.get("decision_id")
            }
            log("==== PIPELINE COMPLETE ====")
            return final_response

        except Exception as e:
            log(f"PIPELINE EXCEPTION: {e}")
            traceback.print_exc(file=sys.stderr)
            return {
                "mode": "typing",
                "expressive_text": "[softly] I... seem to have encountered an error. Please give me a moment.",
                "error": str(e)
            }

    async def _log_exchange(self, response_text: str) -> None:
        input_event_id = str(uuid4())
        await add_node(
            labels=["SoulInput"],
            properties={ "event_id": input_event_id, "user_id": self.user_id, "phrase_event_id": self.phrase_event_id, "timestamp": now_iso(), "text": self.user_input },
        )
        response_event_id = str(uuid4())
        await add_node(
            labels=["SoulResponse"],
            properties={ "event_id": response_event_id, "user_id": self.user_id, "phrase_event_id": self.phrase_event_id, "timestamp": now_iso(), "text": response_text, "arm_id": self.champion_arm_id, "episode_id": self.episode_id },
        )
        await add_relationship(
            {"label": "SoulInput", "match": {"event_id": input_event_id}},
            {"label": "SoulResponse", "match": {"event_id": response_event_id}},
            "GENERATES",
        )
        if self.phrase_event_id:
            await add_relationship(
                {"label": "SoulPhrase", "match": {"event_id": self.phrase_event_id}},
                {"label": "SoulResponse", "match": {"event_id": response_event_id}},
                "RESPONSE_FOR",
            )