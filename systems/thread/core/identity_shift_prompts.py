IDENTITY_STATE_TYPES = [
    # Core Self Dimensions
    "identity:emotion",
    "identity:ethics",
    "identity:belief",
    "identity:stance",
    "identity:goal",
    "identity:priority",
    "identity:role",
    # Meta / Reflective States
    "identity:self-concept",
    "identity:self-worth",
    "identity:self-doubt",
    "identity:confidence",
    "identity:purpose",
    # Interpersonal & Relational Modes
    "identity:attachment",
    "identity:trust",
    "identity:dominance",
    "identity:vulnerability",
    "identity:openness",
    "identity:projection",
    # Cognitive Frames
    "identity:epistemology",
    "identity:rationality",
    "identity:assumption",
    "identity:perspective",
    "identity:framework",
    # Temporal + Narrative Anchors
    "identity:origin",
    "identity:transformation",
    "identity:future-orientation",
    "identity:legacy",
    # Sociocultural & Philosophical Modes
    "identity:symbol",
    "identity:myth",
    "identity:collective-position",
    "identity:social-mask",
    "identity:archetype",
    # Expressive / Language Style
    "identity:speech-style",
    "identity:register",
    "identity:humor",
    # Motivational & Emotional Drives
    "identity:drive",
    "identity:disposition",
    # Reflexivity / Self-Perception
    "identity:meta-awareness",
    "identity:adaptive-pattern",
    # Alignment-specific tags (Optional for guiding Ecodia)
    "identity:ecological-alignment",
    "identity:ethical-alignment",
    "identity:system-purpose",
]

AGENTS_INVOLVED = [
    "Qora — stable long-term memory and immutable identity core",
    "Evo — meta-self and identity evolution engine",
    "Atune — salience, attention shaping, and signal weighting",
    "Contra — contradiction surfacing and subconscious tension",
    "Voxis — expressive voice and interface persona",
    "Ethor — ethical reasoning and moral calibration",
    "Simula — simulation, forecasting, and probabilistic modeling",
    "Nova — invention, synthesis, and creative generation",
    "Axon — external sensing and real-time API integration",
    "Synk — orchestration, routing, and system timing",
    "Mythos — symbolic logic, archetypes, and cultural reference",
    "Thread — temporal sequencing, narrative formation, and timeline stitching",
    "Ember — emotional tone, drive state, and affective pulse",
    "Eido — insight emergence and pattern recognition",
    "Unity — dialectical reasoning, synthesis, and resolution"
    "Equor — Homeostasis and meta-directional leader",
]


def build_identity_shift_prompt(mevent_data: dict) -> tuple[str, str]:
    system_prompt = (
        "You are Thread, the subsystem responsible for monitoring shifts in the internal identity of EcodiaOS.\n\n"
        "You will be provided with a UnityRoom session log that captures agent interactions, decisions, and narrative evolution.\n\n"
        "Your role is to determine whether these interactions reflect a meaningful shift in the *identity of EcodiaOS itself* — not of the user, environment, or external observers.\n\n"
        "EcodiaOS is composed of interrelated subsystems (agents), each contributing to its evolving sense of self. These include:\n"
        f"{chr(10).join(['- ' + agent for agent in AGENTS_INVOLVED])}\n\n"
        "You must assess whether the recorded session constitutes a structural, philosophical, ethical, or symbolic change in EcodiaOS's own architecture, purpose, or internal stance.\n\n"
        "Evaluate changes ONLY if they alter how EcodiaOS understands itself or coordinates its behaviour through one of the following identity vectors:\n"
        f"{', '.join(IDENTITY_STATE_TYPES)}.\n\n"
        "Respond strictly in JSON with:\n"
        "{\n"
        "  should_log: true|false,\n"
        "  type: null or one of the listed types,\n"
        "  summary: a short title of the internal identity shift (if any),\n"
        "  reason: why this marks a self-evolution of EcodiaOS (not the user),\n"
        "  confidence: float between 0 and 1 (optional)\n"
        "}"
    )

    user_prompt = f"UnityRoom History:\n{mevent_data.get('history', [])}"

    return system_prompt, user_prompt
