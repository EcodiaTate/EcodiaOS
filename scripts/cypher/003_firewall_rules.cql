MATCH (p:PolicyArm {id:'creative_claude3'})
MERGE (p)-[:HAS_CONSTRAINT]->(:Rule {property:'risk', operator:'NOT_EQUALS', value:'high', rejection_reason:'No creative exploration at HIGH risk'});

MATCH (p:PolicyArm {id:'noop_arm'})
MERGE (p)-[:HAS_CONSTRAINT]->(:Rule {property:'context.data_domains', operator:'NOT_CONTAINS', value:'sensitive_pii', rejection_reason:'No-Op forbidden on PII'})
