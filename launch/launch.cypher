UNWIND [
  {k:'axon.API_on_demand.enabled', t:'bool', v:'true'},
  {k:'axon.API_runner.enabled', t:'bool', v:'true'},
  {k:'evo.conflict_scan.enabled', t:'bool', v:'true'},
  {k:'evo.tool_experiment.enabled', t:'bool', v:'true'},
  {k:'evo.evolve_from_conflict.enabled', t:'bool', v:'true'},
  {k:'unity.room.enabled', t:'bool', v:'true'},
  {k:'simula.codegen.enabled', t:'bool', v:'true'},
  {k:'simula.tools.enabled', t:'bool', v:'true'}
] AS x
MERGE (f:Flag {key: x.k})
ON CREATE SET
  f.type = x.t,
  f.value_json = x.v,
  f.default_json = x.v,
  f.state = 'active',
  f.updated_at = timestamp();

