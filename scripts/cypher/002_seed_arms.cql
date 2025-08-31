UNWIND [
  {id:'noop_arm', mode:'DEFAULT_MODE', cfg:{model:'gpt-4o', temperature:0.2, max_tokens:1024, is_safe_fallback:true}},
  {id:'balanced_gpt4o', mode:'DEFAULT_MODE', cfg:{model:'gpt-4o', temperature:0.5, max_tokens:4096}},
  {id:'creative_claude3', mode:'EXPLORATION_MODE', cfg:{model:'claude-3-opus', temperature:1.2, max_tokens:4096}},
  {id:'conservative_gpt4', mode:'SAFE_MODE', cfg:{model:'gpt-4', temperature:0.2, max_tokens:1024, is_safe_fallback:true}}
] AS a
MERGE (p:PolicyArm {id:a.id})
ON CREATE SET p.arm_id=a.id, p.mode=a.mode, p.config=a.cfg, p.created_at=datetime()
