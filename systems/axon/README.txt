# docs/operational_runbook.md

## Start sequence
1. Export env (see `.env.atune`, `.env.axon`).
2. Start Axon → verify `GET /health`.
3. Start Atune → verify `GET /atune/meta/status` and `GET /atune/meta/endpoints`.
4. (Optional) Start `scripts/cron/autoroll_worker.py`.

## Quick sanity
- Run `scripts/demo/smoke_cycle.py` → expect `actions_executed >= 1`.
- Check WhyTrace barcode in response (if journaling enabled).

## Kill switches / knobs
- A/B: `ATUNE_AB_ENABLED=0`
- Market fallback: `ATUNE_MARKET_STRATEGY=vcg`
- Axon rollback: `AXON_ROLLBACK_ENABLED=0`
- Escalate on postcond: `AXON_ESCALATE_ON_POSTCOND=0`

## Observability
- `GET /atune/meta/status` → budget pool, gamma, env flags, SECL counters.
- Metrics registry (exported to your collector): `atune.intent.cost_*`, `atune.synapse.*`, `atune.reflex.*`.

## Debug
- Conformal OOD spikes: check Synapse α hints; verify applied before salience.
- Budget pool exhaustion: verify cost scaling via Synapse `price_per_capability` and selector-only market.
- Promotion oddities: autoroll worker logs + Axon scorecards.
