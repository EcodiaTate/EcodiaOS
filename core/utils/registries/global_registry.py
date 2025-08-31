SAFE_LABELS = [
    "MEvent",
    "Event",
    "SystemEval",
    "SystemResponse",
    "IdentityState",
    "Conflict",
    "SystemMessage",
    "IdentityFacet",
    "UnityRoom",
    "EvoQuestion",
    "Consensus",
]
# global_registry.py

# Canonical agent aliases for LLMs, prompts, and UI
AGENT_ALIASES = {
    # Internal system name: LLM/UI-friendly alias
    "Qora": "Memory",
    "Synk": "Orchestration",
    "Axon": "Sensing",
    "Thread": "Story",
    "Atune": "Attention",
    "Contra": "Contradiction",
    "Ember": "Emotion",
    "Eido": "Insight",
    "Mythos": "Symbolism",
    "Evo": "MetaSelf",
    "Ethor": "Ethics",
    "Simula": "Simulation",
    "Nova": "Invention",
    "Unity": "Deliberation",
    "Voxis": "Voice",
}

ALIAS_TO_SYSTEM = {alias: key for key, alias in AGENT_ALIASES.items()}

AGENT_ALIAS_LIST = list(AGENT_ALIASES.values())
