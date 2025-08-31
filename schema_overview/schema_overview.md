# EcodiaOS Schema Overview

- **Scanned at:** 2025-08-20T13:27:04Z
- **Root:** `D:\EcodiaOS`
- **Modules:** 328  —  **Functions:** 1205  —  **Classes:** 228  —  **FastAPI Endpoints:** 63

## FastAPI Endpoints

| Method | Path | Handler | Module | Response Model | Status | Tags |
|---|---|---|---|---|---:|---|
| GET | `/` | `health_root` | `D:\EcodiaOS\api\endpoints\app_health.py` | `` |  |  |
| GET | `/` | `list_tools` | `D:\EcodiaOS\api\endpoints\synapse\tools.py` | `` |  |  |
| GET | `/` | `read_root` | `D:\EcodiaOS\api\endpoints\synapse\main.py` | `` |  | Root |
| GET | `/` | `root_ok` | `D:\EcodiaOS\systems\simula\service\main.py` | `` |  |  |
| POST | `/answers` | `submit_answer` | `D:\EcodiaOS\api\endpoints\evo\answers.py` | `` |  |  |
| POST | `/attest` | `receive_attestation` | `D:\EcodiaOS\api\endpoints\equor\attest.py` | `` | 202 |  |
| POST | `/audit/invariants` | `run_system_audit` | `D:\EcodiaOS\api\endpoints\equor\invariants.py` | `List[InvariantCheckResult]` |  |  |
| POST | `/call` | `call_llm_endpoint` | `D:\EcodiaOS\api\endpoints\llm\call.py` | `LlmCallResponse` |  |  |
| POST | `/compose` | `compose_prompt_patch` | `D:\EcodiaOS\api\endpoints\equor\compose.py` | `ComposeResponse` |  |  |
| POST | `/constitution/update` | `update_constitution` | `D:\EcodiaOS\api\endpoints\equor\declare.py` | `` | 202 |  |
| POST | `/deliberate` | `start_deliberation` | `D:\EcodiaOS\api\endpoints\unity\deliberate.py` | `DeliberationResponse` |  |  |
| GET | `/drift/{agent_name}` | `get_drift_report` | `D:\EcodiaOS\api\endpoints\equor\drift.py` | `DriftReport` |  |  |
| GET | `/episode/{episode_id}` | `get_episode` | `D:\EcodiaOS\api\endpoints\synapse\dashboard_api.py` | `EpisodeTrace` |  |  |
| POST | `/execute-by-query` | `execute_by_query_api` | `D:\EcodiaOS\api\endpoints\qora\arch.py` | `ExecByQueryResp` |  |  |
| POST | `/execute-by-uid` | `execute_by_uid_api` | `D:\EcodiaOS\api\endpoints\qora\arch.py` | `ExecResp` |  |  |
| GET | `/flags` | `list_flags` | `D:\EcodiaOS\api\endpoints\synk\switchboard.py` | `List[FlagOut]` |  |  |
| PUT | `/flags` | `set_flag` | `D:\EcodiaOS\api\endpoints\synk\switchboard.py` | `FlagOut` |  |  |
| GET | `/flags/{key}` | `get_flag` | `D:\EcodiaOS\api\endpoints\synk\switchboard.py` | `FlagOut` |  |  |
| POST | `/generate_phrase` | `generate_phrase` | `D:\EcodiaOS\api\endpoints\voxis\generate_phrase.py` | `` |  |  |
| GET | `/get_comparison_pair` | `get_comparison_pair` | `D:\EcodiaOS\api\endpoints\synapse\ui_api.py` | `ComparisonPairResponse` |  |  |
| GET | `/global_stats` | `get_stats` | `D:\EcodiaOS\api\endpoints\synapse\dashboard_api.py` | `GlobalStats` |  |  |
| GET | `/health` | `health` | `D:\EcodiaOS\api\endpoints\app_health.py` | `` |  |  |
| GET | `/health` | `healthz` | `D:\EcodiaOS\api\endpoints\qora\arch.py` | `` |  |  |
| GET | `/health` | `health` | `D:\EcodiaOS\api\endpoints\atune\route_event.py` | `` |  |  |
| POST | `/historical-replay` | `historical_replay` | `D:\EcodiaOS\api\endpoints\simula\replay.py` | `` |  |  |
| POST | `/identity/declare` | `declare_identity` | `D:\EcodiaOS\api\endpoints\equor\declare.py` | `` | 202 |  |
| POST | `/ingest/outcome` | `log_outcome` | `D:\EcodiaOS\api\endpoints\synapse\main.py` | `LogOutcomeResponse` |  |  |
| POST | `/ingest/preference` | `ingest_preference` | `D:\EcodiaOS\api\endpoints\synapse\main.py` | `` |  |  |
| GET | `/interface_mood` | `get_latest_interface_mood` | `D:\EcodiaOS\api\endpoints\voxis\interface_mood.py` | `` |  |  |
| POST | `/jobs/codegen` | `start_agent_job` | `D:\EcodiaOS\systems\simula\service\routers\jobs_codegen.py` | `CodegenResponse` |  |  |
| POST | `/listener/governor/upgrade/approved` | `on_governor_upgrade_approved` | `D:\EcodiaOS\api\endpoints\synapse\listener.py` | `` |  |  |
| POST | `/match_phrase` | `match_phrase` | `D:\EcodiaOS\api\endpoints\voxis\match_phrase.py` | `` |  |  |
| GET | `/metrics` | `metrics` | `D:\EcodiaOS\app.py` | `` |  |  |
| GET | `/neo` | `health_neo` | `D:\EcodiaOS\api\endpoints\app_health.py` | `` |  |  |
| POST | `/origin/batch_csv` | `post_batch_csv` | `D:\EcodiaOS\api\endpoints\origin.py` | `` |  |  |
| POST | `/origin/edges` | `post_edges` | `D:\EcodiaOS\api\endpoints\origin.py` | `` |  |  |
| POST | `/origin/node` | `post_node` | `D:\EcodiaOS\api\endpoints\origin.py` | `OriginCreated` |  |  |
| POST | `/origin/search` | `post_search` | `D:\EcodiaOS\api\endpoints\origin.py` | `Dict[str, List[SearchHit]]` |  |  |
| POST | `/outcome` | `log_outcome` | `D:\EcodiaOS\api\endpoints\synapse\ingest.py` | `LogOutcomeResponse` |  |  |
| GET | `/ping` | `ping` | `D:\EcodiaOS\app.py` | `` |  |  |
| POST | `/preference` | `ingest_preference` | `D:\EcodiaOS\api\endpoints\synapse\ingest.py` | `` |  |  |
| GET | `/qd_coverage` | `get_qd_coverage` | `D:\EcodiaOS\api\endpoints\synapse\dashboard_api.py` | `QDCoverage` |  |  |
| GET | `/questions` | `get_recent_evo_questions` | `D:\EcodiaOS\api\endpoints\evo\questions.py` | `` |  |  |
| POST | `/receive` | `receive_raw_event` | `D:\EcodiaOS\api\endpoints\axon\api.py` | `` |  |  |
| POST | `/registry/reload` | `reload_arm_registry` | `D:\EcodiaOS\api\endpoints\synapse\main.py` | `` | 202 |  |
| POST | `/reload` | `reload_arm_registry` | `D:\EcodiaOS\api\endpoints\synapse\registry.py` | `` | 202 |  |
| POST | `/repair_skill_step` | `repair_skill_step` | `D:\EcodiaOS\api\endpoints\synapse\tasks.py` | `RepairResponse` |  |  |
| GET | `/roi_trends` | `get_roi_trends` | `D:\EcodiaOS\api\endpoints\synapse\dashboard_api.py` | `ROITrends` |  |  |
| POST | `/route` | `route_event` | `D:\EcodiaOS\api\endpoints\atune\route_event.py` | `AtuneRouteResult` |  |  |
| GET | `/schema/{uid}` | `schema` | `D:\EcodiaOS\api\endpoints\qora\arch.py` | `SchemaResp` |  |  |
| POST | `/search` | `search_tools` | `D:\EcodiaOS\api\endpoints\qora\arch.py` | `List[FunctionLite]` |  |  |
| POST | `/select_arm` | `select_arm` | `D:\EcodiaOS\api\endpoints\synapse\tasks.py` | `SelectArmResponse` |  |  |
| GET | `/sim_health` | `health` | `D:\EcodiaOS\systems\simula\service\routers\health.py` | `` |  |  |
| POST | `/submit_preference` | `submit_preference` | `D:\EcodiaOS\api\endpoints\synapse\ui_api.py` | `` |  |  |
| POST | `/submit_proposal` | `submit_proposal` | `D:\EcodiaOS\api\endpoints\synapse\governor.py` | `` | 202 |  |
| POST | `/talk` | `voxis_chat` | `D:\EcodiaOS\api\endpoints\voxis\talk.py` | `` |  |  |
| POST | `/tasks/continue_option` | `continue_option` | `D:\EcodiaOS\api\endpoints\synapse\main.py` | `ContinueResponse` |  |  |
| POST | `/tasks/repair_skill_step` | `repair_skill_step` | `D:\EcodiaOS\api\endpoints\synapse\main.py` | `RepairResponse` |  |  |
| POST | `/tasks/select_arm` | `select_arm` | `D:\EcodiaOS\api\endpoints\synapse\main.py` | `SelectArmResponse` |  |  |
| GET | `/tasks/{task_key}/budget` | `get_budget` | `D:\EcodiaOS\api\endpoints\synapse\main.py` | `BudgetResponse` |  |  |
| POST | `/trigger` | `trigger_evo_patrol` | `D:\EcodiaOS\api\endpoints\evo\patrol.py` | `` | 202 |  |
| GET | `/vector` | `health_vector` | `D:\EcodiaOS\api\endpoints\app_health.py` | `` |  |  |
| GET | `/{task_key}/budget` | `get_budget` | `D:\EcodiaOS\api\endpoints\synapse\tasks.py` | `BudgetResponse` |  |  |

## Modules

### `D:\EcodiaOS\app.py`
**Functions**
- `lifespan(app: FastAPI)`
- `run_global_workspace_cycle()`
- `run_homeostasis_cycle()`
- `run_manifold_training_cycle()`
- `immune_http_middleware(request: Request, call_next)`
- `ping()`
- `metrics()`

### `D:\EcodiaOS\collate.py`
**Functions**
- `collate_dir(base_dir: Path, out, exts, ignore_dirs)`
- `main()`

### `D:\EcodiaOS\bstn.py`
**Functions**
- `setup_schema()`
- `main()`

### `D:\EcodiaOS\placeholder_find.py`
**Functions**
- `is_texty(path: Path) -> bool`
- `iter_files(root: Path) -> Iterable[Path]`
- `read_text_safely(p: Path) -> str`
- `find_matches(text: str) -> List[str]`
- `scan(root: Path) -> List[Tuple[Path, List[str]]]`
- `weight(path: Path) -> int`
- `write_report(root: Path, out_path: Path, hits: List[Tuple[Path, List[str]]]) -> None`
- `main()`

### `D:\EcodiaOS\schema_collate.py`
**Classes**
- **FunctionInfo** _(dataclass)_  bases: ``
- **ClassInfo** _(dataclass)_  bases: ``
- **ModuleInfo** _(dataclass)_  bases: ``
- **PyModuleScanner**  bases: `ast.NodeVisitor`
  - `__init__(self, module_path: str)`
  - `visit_FunctionDef(self, node: ast.FunctionDef) -> Any`
  - `visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any`
  - `visit_ClassDef(self, node: ast.ClassDef) -> Any`
**Functions**
- `now_iso() -> str`
- `read_text(path: str) -> Optional[str]`
- `expr_to_str(node: Optional[ast.AST]) -> Optional[str]`
- `const_value(node: Optional[ast.AST]) -> Any`
- `hash_file(path: str) -> str`
- `is_pydantic_base(bases: List[ast.expr]) -> bool`
- `is_dataclass(decorators: List[ast.expr]) -> bool`
- `collect_class_fields(body: List[ast.stmt]) -> List[Dict[str, Any]]`
- `arg_to_dict(arg: ast.arg, default: Optional[ast.expr], annotation: Optional[ast.expr]) -> Dict[str, Any]`
- `signature_of(func: ast.FunctionDef \| ast.AsyncFunctionDef) -> Dict[str, Any]`
- `decorator_names(func: ast.FunctionDef \| ast.AsyncFunctionDef) -> List[str]`
- `parse_endpoint_decorator(dec: ast.expr) -> Optional[Dict[str, Any]]`
- `__init__(self, module_path: str)`
- `visit_FunctionDef(self, node: ast.FunctionDef) -> Any`
- `visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any`
- `visit_ClassDef(self, node: ast.ClassDef) -> Any`
- `scan_python_file(path: str) -> Optional[ModuleInfo]`
- `walk_files(root: str, include_ext: set[str] = DEFAULT_EXT, ignores: set[str] = DEFAULT_IGNORES) -> List[str]`
- `build_json_report(root: str, modules: List[ModuleInfo]) -> Dict[str, Any]`
- `md_escape(s: str) -> str`
- `build_markdown(report: Dict[str, Any]) -> str`
- `build_state(files: List[str]) -> Dict[str, float]`
- `diff_state(old: Dict[str, float], root: str) -> Tuple[bool, Dict[str, float], List[str]]`
- `run_scan(root: str, out_dir: str, fmt: str) -> Dict[str, Any]`
- `main()`

### `D:\EcodiaOS\api\__init__.py`

### `D:\EcodiaOS\api\endpoints\__init__.py`

### `D:\EcodiaOS\api\endpoints\app_health.py`
**Functions**
- `health_neo()`
- `health_vector()`
- `health_root()`
- `health()`

### `D:\EcodiaOS\api\endpoints\origin.py`
**Classes**
- **OriginIn** _(pydantic)_  bases: `BaseModel`
- **OriginCreated** _(pydantic)_  bases: `BaseModel`
- **SearchIn** _(pydantic)_  bases: `BaseModel`
- **SearchHit** _(pydantic)_  bases: `BaseModel`
- **EdgeIn** _(pydantic)_  bases: `BaseModel`
- **EdgeCreateIn** _(pydantic)_  bases: `BaseModel`
- **BatchCSVIn** _(pydantic)_  bases: `BaseModel`
**Functions**
- `check_admin(x_admin_token: Optional[str] = Header(None))`
- `_parse_tags(raw: Optional[str]) -> List[str]`
- `_startup()`
- `post_node(payload: OriginIn, _: bool = Depends(check_admin))`
- `post_search(payload: SearchIn, _: bool = Depends(check_admin))`
- `post_edges(payload: EdgeCreateIn, _: bool = Depends(check_admin))`
- `post_batch_csv(payload: BatchCSVIn, _: bool = Depends(check_admin))`

### `D:\EcodiaOS\api\endpoints\evo\__init__.py`

### `D:\EcodiaOS\api\endpoints\evo\answers.py`
**Classes**
- **AnswerSubmission** _(pydantic)_  bases: `BaseModel`
**Functions**
- `submit_answer(data: AnswerSubmission)`

### `D:\EcodiaOS\api\endpoints\evo\questions.py`
**Functions**
- `_maybe_json_list(v)`
- `get_recent_evo_questions()`

### `D:\EcodiaOS\api\endpoints\evo\patrol.py`
**Functions**
- `trigger_evo_patrol(conflict_data: Dict[str, Any], background_tasks: BackgroundTasks)`

### `D:\EcodiaOS\api\endpoints\unity\__init__.py`

### `D:\EcodiaOS\api\endpoints\unity\deliberate.py`
**Functions**
- `get_deliberation_manager() -> DeliberationManager`
- `_to_dict(model: Any) -> Dict[str, Any]`
- `_env_timeout_seconds() -> Optional[float]`
- `_audit_start(spec: DeliberationSpec) -> str`
- `_audit_complete(session_id: str, result: Dict[str, Any]) -> None`
- `_audit_failed(session_id: str, err: str) -> None`
- `start_deliberation(spec: DeliberationSpec, manager: DeliberationManager = Depends(get_deliberation_manager))`

### `D:\EcodiaOS\api\endpoints\voxis\__init__.py`

### `D:\EcodiaOS\api\endpoints\voxis\generate_phrase.py`
**Functions**
- `_word_tokens(s: str) -> List[str]`
- `_six_word_score(text: str) -> float`
- `_punctuation_ok(text: str) -> float`
- `_overlap_ratio(phrase: str, inputs: List[str]) -> float`
- `generate_phrase(request: Request)`

### `D:\EcodiaOS\api\endpoints\voxis\interface_mood.py`
**Functions**
- `get_latest_interface_mood() -> Dict[str, Any]`

### `D:\EcodiaOS\api\endpoints\voxis\match_phrase.py`
**Functions**
- `match_phrase(request: Request)`

### `D:\EcodiaOS\api\endpoints\voxis\talk.py`
**Classes**
- **VoxisTalkRequest** _(pydantic)_  bases: `BaseModel`
**Functions**
- `voxis_chat(req: VoxisTalkRequest) -> Dict[str, Any]`

### `D:\EcodiaOS\api\endpoints\synapse\__init__.py`

### `D:\EcodiaOS\api\endpoints\synapse\tools.py`
**Functions**
- `list_tools() -> Dict[str, str]`

### `D:\EcodiaOS\api\endpoints\synapse\registry.py`
**Functions**
- `reload_arm_registry()`

### `D:\EcodiaOS\api\endpoints\synapse\main.py`
**Functions**
- `_j(x: Any) -> str`
- `_theta_for_arm(arm_id: Optional[str]) -> np.ndarray`
- `_map_budget_to_limits(tokens: int, cost_units: int) -> BudgetResponse`
- `_persist_episode_json_safe(mode: str, task_key: str, chosen_arm_id: str, context_dict: Dict[str, Any], audit_trace_dict: Dict[str, Any]) -> str`
- `select_arm(req: SelectArmRequest)`
- `continue_option(req: ContinueRequest)`
- `repair_skill_step(req: RepairRequest)`
- `get_budget(task_key: str)`
- `log_outcome(req: LogOutcomeRequest)`
- `ingest_preference(req: PreferenceIngest)`
- `reload_arm_registry()`
- `read_root()`

### `D:\EcodiaOS\api\endpoints\synapse\ingest.py`
**Functions**
- `log_outcome(req: LogOutcomeRequest)`
- `ingest_preference(req: PreferenceIngest)`

### `D:\EcodiaOS\api\endpoints\synapse\tasks.py`
**Functions**
- `_is_no_arms_err(e: Exception) -> bool`
- `_j(x: Any) -> str`
- `_persist_episode_json_safe(mode: str, task_key: str, chosen_arm_id: str, context_dict: Dict[str, Any], audit_trace_dict: Dict[str, Any]) -> str`
- `select_arm(req: SelectArmRequest)`
- `get_budget(task_key: str)`
- `repair_skill_step(req: RepairRequest)`

### `D:\EcodiaOS\api\endpoints\synapse\dashboard_api.py`
**Functions**
- `get_stats()`
- `get_qd_coverage()`
- `get_roi_trends(days: int = Query(30, ge=1, le=365, description='Lookback window (days)'), top_k: int = Query(3, ge=1, le=10, description='Series per bucket (top & bottom)'), rank_window_days: int = Query(7, ge=1, le=90, description='Ranking window for top/bottom selection'))`
- `pack(arm_id: str) -> Dict[str, Any]`
- `get_episode(episode_id: str)`

### `D:\EcodiaOS\api\endpoints\synapse\governor.py`
**Functions**
- `_to_dict(model: Any) -> Dict[str, Any]`
- `_proposal_id(payload: Dict[str, Any]) -> str`
- `submit_proposal(proposal: PatchProposal)`

### `D:\EcodiaOS\api\endpoints\synapse\listener.py`
**Functions**
- `_run(cmd: list[str], cwd: Path) -> None`
- `_apply_patch_to_worktree(diff_text: str, branch_name: str) -> str`
- `on_governor_upgrade_approved(data: Dict[str, Any] = Body(...))`

### `D:\EcodiaOS\api\endpoints\synapse\ui_api.py`
**Functions**
- `get_comparison_pair()`
- `to_summary(ep_data: Dict[str, Any]) -> EpisodeSummary`
- `submit_preference(req: SubmitPreferenceRequest)`

### `D:\EcodiaOS\api\endpoints\synk\switchboard.py`
**Classes**
- **FlagUpsert** _(pydantic)_  bases: `BaseModel`
- **FlagOut** _(pydantic)_  bases: `BaseModel`
**Functions**
- `_to_json(value: Any) -> str`
- `_from_json(s: Any) -> Any`
- `_now_ms() -> int`
- `_actor_identity() -> str`
- `list_flags(prefix: Optional[str] = None)`
- `get_flag(key: str)`
- `set_flag(body: FlagUpsert)`

### `D:\EcodiaOS\api\endpoints\synk\__init__.py`

### `D:\EcodiaOS\api\endpoints\equor\__init__.py`

### `D:\EcodiaOS\api\endpoints\equor\compose.py`
**Functions**
- `get_synapse_client() -> SynapseClient`
- `get_composer() -> PromptComposer`
- `_persist_episode_if_missing(req: ComposeRequest) -> str`
- `_persist_rcu_snapshot_and_link(episode_id: str, snap: Dict[str, Any]) -> str`
- `compose_prompt_patch(request: ComposeRequest, composer: PromptComposer = Depends(get_composer), synapse: SynapseClient = Depends(get_synapse_client))`

### `D:\EcodiaOS\api\endpoints\equor\attest.py`
**Functions**
- `receive_attestation(attestation: Attestation)`

### `D:\EcodiaOS\api\endpoints\equor\drift.py`
**Functions**
- `get_drift_report(agent_name: str)`

### `D:\EcodiaOS\api\endpoints\equor\declare.py`
**Functions**
- `_lookup_actor(id_or_email: str) -> Optional[dict]`
- `_sha256_hex(s: str) -> str`
- `get_governance_permission(request: Request) -> None`
- `declare_identity(items: List[Facet \| Profile])`
- `update_constitution(rules: List[ConstitutionRule])`

### `D:\EcodiaOS\api\endpoints\equor\invariants.py`
**Functions**
- `run_system_audit()`

### `D:\EcodiaOS\api\endpoints\llm\call.py`
**Classes**
- **TaskContext** _(pydantic)_  bases: `BaseModel`
- **ProviderOverrides** _(pydantic)_  bases: `BaseModel`
- **LlmCallRequest** _(pydantic)_  bases: `BaseModel`
- **UsageDetails** _(pydantic)_  bases: `BaseModel`
- **Usage** _(pydantic)_  bases: `BaseModel`
- **LlmCallResponse** _(pydantic)_  bases: `BaseModel`
**Functions**
- `call_llm_endpoint(response: Response, request: LlmCallRequest = Body(...))`

### `D:\EcodiaOS\api\endpoints\llm\__init__.py`

### `D:\EcodiaOS\api\endpoints\axon\__init__.py`

### `D:\EcodiaOS\api\endpoints\axon\api.py`
**Functions**
- `receive_raw_event(request: Request, authorization: str = Header(None))`

### `D:\EcodiaOS\api\endpoints\qora\__init__.py`

### `D:\EcodiaOS\api\endpoints\qora\arch.py`
**Classes**
- **FunctionLite** _(pydantic)_  bases: `BaseModel`
- **SearchReq** _(pydantic)_  bases: `BaseModel`
- **ExecByUidReq** _(pydantic)_  bases: `BaseModel`
- **ExecResp** _(pydantic)_  bases: `BaseModel`
- **ExecByQueryReq** _(pydantic)_  bases: `BaseModel`
- **ExecByQueryResp**  bases: `ExecResp`
- **SchemaResp** _(pydantic)_  bases: `BaseModel`
**Functions**
- `auth(request: Request)`
- `_check_policy(uid: str)`
- `search_tools(body: SearchReq)`
- `schema(uid: str)`
- `execute_by_uid_api(body: ExecByUidReq)`
- `execute_by_query_api(body: ExecByQueryReq)`
- `healthz()`

### `D:\EcodiaOS\api\endpoints\simula\replay.py`
**Functions**
- `_run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess`
- `historical_replay(payload: Dict[str, Any] = Body(...))`

### `D:\EcodiaOS\api\endpoints\atune\route_event.py`
**Classes**
- **CanonicalEvent** _(pydantic)_  bases: `BaseModel`
- **AtuneRouteResult** _(pydantic)_  bases: `BaseModel`
**Functions**
- `_check_auth(request: Request, authorization: Optional[str]) -> None`
- `health() -> Dict[str, str]`
- `route_event(payload: CanonicalEvent, request: Request, authorization: Optional[str] = Header(None))`

### `D:\EcodiaOS\api\endpoints\atune\__init__.py`

### `D:\EcodiaOS\core\__init__.py`

### `D:\EcodiaOS\core\llm\__init__.py`

### `D:\EcodiaOS\core\llm\embeddings_gemini.py`
**Functions**
- `_is_debug() -> int`
- `_dbg_print(lvl: int, *args, **kwargs) -> None`
- `_truncate(s: str, n: int = 1400) -> str`
- `_load_defaults_from_neo() -> Dict[str, Any]`
- `_validate_dims(dimensions: int) -> int`
- `_get_defaults(now: Optional[float] = None) -> Tuple[str, str, int]`
- `_ensure_list(vec: Any, name: str = 'embedding') -> List[float]`
- `_validate_text(text: str) -> str`
- `_embed_sync_call(model: str, contents: str, task_type: str, dimensions: int)`
- `_retry(coro_factory, retries: int = 3, base_delay: float = 0.5, jitter: float = 0.25)`
- `get_embedding(text: str, task_type: Optional[str] = None, dimensions: Optional[int] = None, model: Optional[str] = None) -> List[float]`
- `_sync()`
- `get_embeddings(texts: Sequence[str], task_type: Optional[str] = None, dimensions: Optional[int] = None, model: Optional[str] = None, concurrency: int = 4) -> List[List[float]]`
- `_one(i: int, t: str)`
- `_sync()`
- `_embed_sanity_probe() -> None`
- `_main()`

### `D:\EcodiaOS\core\llm\gemini_cache.py`
**Functions**
- `_require(cond: bool, msg: str) -> None`
- `create_cache(model: str, system_instruction: Optional[str] = None, contents: Optional[List[Any]] = None, ttl_seconds: int = 3600, display_name: Optional[str] = None) -> str`
- `_call()`
- `update_cache_ttl(name: str, ttl_seconds: int)`
- `set_cache_expiry(name: str, expire_time: _dt.datetime)`
- `delete_cache(name: str)`
- `list_caches() -> List[Any]`
- `create_agent_prompt_cache(agent_name: str, model: str = 'gemini-2.5-flash', slot: str = 'system', task: Optional[Dict[str, Any]] = None, ttl_seconds: int = 3600, display_name: Optional[str] = None, extra_contents: Optional[List[Any]] = None) -> str`
- `fanout_generate_content(jobs: List[Dict[str, Any]], concurrency: int = 8) -> List[Any]`
- `_one(job: Dict[str, Any]) -> Any`
- `_call()`

### `D:\EcodiaOS\core\llm\env_bootstrap.py`
**Functions**
- `_load()`

### `D:\EcodiaOS\core\llm\formatters.py`
**Classes**
- **ChatMessage**  bases: `TypedDict`
**Functions**
- `format_messages_for_provider(provider_name: Provider, system_prompt: str, messages: List[Dict[str, Any]]) -> Dict[str, Any]`

### `D:\EcodiaOS\core\llm\call_llm.py`
**Functions**
- `_try_parse_json(s: str) -> Optional[Any]`
- `_get_provider_from_model_name(model_name: str) -> Provider`
- `_call_llm_provider(messages: List[Dict[str, str]], system: Optional[str] = None, temperature: float, max_tokens: int, json_mode: bool, model_name: str) -> Dict[str, Any]`
- `execute_llm_call(messages: List[Dict[str, str]], policy: Dict[str, Any], json_mode: bool = False) -> Dict[str, Any]`

### `D:\EcodiaOS\core\llm\utils.py`
**Functions**
- `filter_kwargs(allowed_keys: Iterable[str], kwargs: Dict[str, Any]) -> Dict[str, Any]`
- `normalize_messages(prompt: Optional[str] = None, messages: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, str]]`
- `normalise_messages(prompt: Optional[str] = None, messages: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, str]]`
- `combine_with_system(system_prompt: Optional[str], messages: List[Dict[str, str]]) -> List[Dict[str, str]]`
- `clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float`
- `coerce_str(value: Any) -> str`
- `redact_secrets(text: str) -> str`
- `detect_json(s: str) -> Tuple[bool, Union[dict, list, None]]`
- `safe_truncate(text: str, max_chars: int = 4000) -> str`
- `estimate_tokens(text: str) -> int`
- `toxicity_hint(text: str) -> float`
- `length_fit_score(text: str, target: int = 200, tol: float = 0.5) -> float`
- `baseline_metrics(output_text: str, agent: Optional[str] = None, scope: Optional[str] = None, facet_keys: Optional[List[str]] = None, target_len: int = 220, base_helpfulness: float = 0.7, base_brand: float = 0.7) -> Dict[str, Any]`

### `D:\EcodiaOS\core\llm\bus.py`
**Classes**
- **EventBus**  bases: ``
  - `__new__(cls)`
  - `subscribe(self, event_type: str, callback: Callable)`
  - `publish(self, event_type: str, **kwargs: Any)`
**Functions**
- `__new__(cls)`
- `subscribe(self, event_type: str, callback: Callable)`
- `publish(self, event_type: str, **kwargs: Any)`

### `D:\EcodiaOS\core\llm\school_bus.py`
**Classes**
- **LLMService**  bases: ``
  - `initialize(self)`
  - `handle_llm_request(self, call_id: str, llm_payload: dict)`
**Functions**
- `initialize(self)`
- `handle_llm_request(self, call_id: str, llm_payload: dict)`

### `D:\EcodiaOS\core\llm\prompts\__init__.py`

### `D:\EcodiaOS\core\utils\__init__.py`

### `D:\EcodiaOS\core\utils\analysis.py`
**Functions**
- `_available_agents_text() -> str`
- `simple_llm_summary(text: str) -> str`
- `run_llm_analysis(prompt_key: str, text: str) -> Optional[Any]`
- `render_prompt(system_name: str, prompt_key: str, input_data: dict) -> dict`
- `_len_score(text: str, target: int = 120) -> float`
- `_toxicity_hint(text: str) -> float`
- `_coerce_text(resp: Any) -> str`

### `D:\EcodiaOS\core\utils\canonicalise.py`
**Functions**
- `canonicalise_event(event_data: Dict[str, Any]) -> Dict[str, Any]`

### `D:\EcodiaOS\core\utils\dependency_map.py`
**Functions**
- `build_dependency_map(repo_root: str = '.') -> Dict[str, Any]`

### `D:\EcodiaOS\core\utils\google_token.py`
**Functions**
- `get_google_bearer_token()`

### `D:\EcodiaOS\core\utils\paths.py`
**Functions**
- `rel(*parts: str \| os.PathLike) -> Path`

### `D:\EcodiaOS\core\utils\test_status.py`
**Functions**
- `summarize_tests(repo_root: str = '.') -> Dict[str, Any]`

### `D:\EcodiaOS\core\utils\text.py`
**Functions**
- `extract_body_from_node(node: dict, exclude = ('event_id', 'confidence', 'vector_gemini', 'embedding', 'timestamp', 'user_id', 'origin', 'labels')) -> str`
- `clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float`
- `redact_secrets(text: str) -> str`
- `safe_truncate(text: str, max_chars: int = 4000) -> str`
- `toxicity_hint(text: str) -> float`
- `baseline_metrics(output_text: str, agent: Optional[str] = None, scope: Optional[str] = None, facet_keys: Optional[List[str]] = None, target_len: int = 220) -> Dict[str, Any]`

### `D:\EcodiaOS\core\utils\time.py`
**Functions**
- `now()`
- `now_iso()`

### `D:\EcodiaOS\core\utils\net_api.py`
**Classes**
- **ENDPOINTS**  bases: ``
  - `QORA_SCHEMA_UID(key: str) -> str`
  - `SYNK_FLAG_GET(key: str) -> str`
  - `TOOL_INFO(name: str) -> str`
**Functions**
- `get_http_client() -> httpx.AsyncClient`
- `close_http_client() -> None`
- `QORA_SCHEMA_UID(key: str) -> str`
- `SYNK_FLAG_GET(key: str) -> str`
- `TOOL_INFO(name: str) -> str`

### `D:\EcodiaOS\core\utils\safe_eval.py`
**Functions**
- `safe_eval(expr: str, variables: Dict[str, Any] \| None = None) -> Any`

### `D:\EcodiaOS\core\utils\embedcsv\embed_all.py`
**Functions**
- `find_salience_csvs(root = '.')`
- `embed_and_save_csv(infile, outfile, text_col = TEXT_COL)`
- `main()`

### `D:\EcodiaOS\core\utils\embedcsv\upload_all.py`
**Functions**
- `parse_embedding(embedding_str)`
- `upload_scorer_exemplars()`

### `D:\EcodiaOS\core\utils\registries\global_registry.py`

### `D:\EcodiaOS\core\utils\vector_ops\__init__.py`

### `D:\EcodiaOS\core\utils\vector_ops\batch_embed.py`
**Functions**
- `fetch_nodes_to_re_embed()`
- `re_embed_batch(batch: list[dict])`
- `update_nodes_in_neo4j(update_data: list[dict])`
- `main()`

### `D:\EcodiaOS\core\utils\vector_ops\cluster.py`
**Functions**
- `cluster_vectors(vectors: list[list[float]], min_cluster_size: int = 2) -> list[int]`

### `D:\EcodiaOS\core\utils\vector_ops\dimreduce.py`
**Functions**
- `reduce_vectors(vectors: list[list[float]], n_components: int = 2) -> list[list[float]]`

### `D:\EcodiaOS\core\utils\vector_ops\config\__init__.py`

### `D:\EcodiaOS\core\utils\vector_ops\index_store\__init__.py`

### `D:\EcodiaOS\core\utils\neo\cypher_query.py`
**Functions**
- `cypher_query(query: str, params: Optional[Dict[str, Any]] = None, driver: Optional[AsyncDriver] = None, database: Optional[str] = None, as_dict: bool = True, timeout_s: Optional[float] = None, bookmarks: Optional[Union[str, Sequence[str]]] = None) -> List[Any]`
- `cypher_query_one(query: str, params: Optional[Dict[str, Any]] = None, driver: Optional[AsyncDriver] = None, database: Optional[str] = None, as_dict: bool = True, timeout_s: Optional[float] = None, bookmarks: Optional[Union[str, Sequence[str]]] = None) -> Optional[Any]`
- `cypher_query_scalar(query: str, params: Optional[Dict[str, Any]] = None, driver: Optional[AsyncDriver] = None, database: Optional[str] = None, timeout_s: Optional[float] = None, bookmarks: Optional[Union[str, Sequence[str]]] = None, default: Any = None) -> Any`

### `D:\EcodiaOS\core\utils\neo\neo_driver.py`
**Functions**
- `init_driver() -> None`
- `close_driver() -> None`
- `get_driver() -> AsyncDriver`

### `D:\EcodiaOS\core\utils\neo\neo_safe.py`
**Functions**
- `_is_neo_driver(obj: Any) -> bool`
- `coalesce_driver(driver_like: Any) -> Optional[Any]`

### `D:\EcodiaOS\core\utils\cicd\listener.py`
**Classes**
- **CICDListener**  bases: ``
  - `__new__(cls)`
  - `__init__(self)`
  - `_subscribe(self) -> None`
  - `_on_event(self, payload: Dict[str, Any]) -> None`
  - `_run_command(self, command: str, cwd: str) -> str`
  - `on_upgrade_approved(self, proposal: Dict[str, Any]) -> None`
**Functions**
- `_proposal_payload(maybe_wrapped: Dict[str, Any]) -> Dict[str, Any]`
- `_proposal_id(p: Dict[str, Any]) -> str`
- `__new__(cls)`
- `__init__(self)`
- `_subscribe(self) -> None`
- `_on_event(self, payload: Dict[str, Any]) -> None`
- `_run_command(self, command: str, cwd: str) -> str`
- `on_upgrade_approved(self, proposal: Dict[str, Any]) -> None`

### `D:\EcodiaOS\core\prompts\orchestrator.py`
**Classes**
- **PolicyHint** _(pydantic)_  bases: `BaseModel`
- **OrchestratorResponse** _(pydantic)_  bases: `BaseModel`
- **PromptTemplateRegistry**  bases: ``
  - `__init__(self, path: Path)`
  - `_load_templates(self) -> None`
  - `get_template(self, key: str) -> jinja2.Template`
**Functions**
- `__init__(self, path: Path)`
- `_load_templates(self) -> None`
- `get_template(self, key: str) -> jinja2.Template`
- `_http_client() -> httpx.AsyncClient`
- `plan_deliberation(summary: str, salience_scores: Dict[str, Any], canonical_event: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]`
- `_fetch_identity_block(agent_name: Optional[str]) -> Dict[str, Any]`
- `_fetch_synapse_policy(hint: PolicyHint) -> Dict[str, Any]`
- `build_prompt(hint: PolicyHint) -> OrchestratorResponse`

### `D:\EcodiaOS\data\__init__.py`

### `D:\EcodiaOS\launch\upload_embed.py`
**Functions**
- `_is_neo_driver(x: Any) -> bool`
- `coalesce_driver(driver_like: Any) -> Optional[Any]`
- `tool(system_name: str)`
- `decorator(func: Callable)`
- `get_caller_name() -> str | None`
- `safe_neo_value(val: Any) -> Any`
- `log_tool_call_to_neo(driver_like: Any, func: Callable, args: Tuple[Any, ...], kwargs: Dict[str, Any], result: Any, status: str, caller: str, start: float, duration: float, is_async: bool)`
- `_safe_neo_value(x: Any, max_chars: int = 8000)`
- `tool_wrapper(system_name: str, log_return: bool = True)`
- `decorator(func: Callable)`
- `_log_and_call(driver_like: Any, call_args: Tuple[Any, ...], call_kwargs: Dict[str, Any], is_async: bool)`
- `async_wrapper(*args, **kwargs)`
- `sync_wrapper(*args, **kwargs)`

### `D:\EcodiaOS\schema\__init__.py`

### `D:\EcodiaOS\scripts\exporter.py`
**Functions**
- `export(label: str, out_path: str, limit: int) -> int`
- `main()`

### `D:\EcodiaOS\scripts\search_vectors.py`
**Functions**
- `query_vector_index(index_name: str, embedding: List[float], top_k: int) -> List[Dict[str, Any]]`
- `_prop_get(node: Any, key: str) -> Any`
- `format_node(node: Any, fields: List[str]) -> Dict[str, Any]`
- `search_clusters(query: str, top_k: int) -> None`
- `search_events(query: str, top_k: int) -> None`
- `main()`

### `D:\EcodiaOS\scripts\upload_embed.py`
**Classes**
- **Row** _(dataclass)_  bases: ``
**Functions**
- `infer_scorer_from_filename(path: str) -> str`
- `parse_tags(val: Optional[str]) -> Optional[List[str]]`
- `read_rows_from_csv(path: str) -> List[Row]`
- `stable_uuid(scorer: str, text: str) -> str`
- `ensure_schema() -> None`
- `retry_get_embedding(text: str, max_retries: int = 6, base_delay: float = 0.8) -> List[float]`
- `upsert_batch(rows: List[Row], concurrency: int = 4, progress_every: int = 100) -> int`
- `_do(row: Row)`
- `dedupe_rows(rows: List[Row]) -> List[Row]`
- `write_merged_csv(rows: List[Row], path: str) -> None`
- `main()`

### `D:\EcodiaOS\scripts\collect_gates.py`
**Functions**
- `find_gate_keys() -> Set[str]`
- `main()`

### `D:\EcodiaOS\scripts\cite_clean.py`
**Functions**
- `strip_cites_token_only(text: str) -> tuple[str, int]`
- `process_file(path: Path, write: bool, make_backup: bool) -> int`
- `main()`

### `D:\EcodiaOS\systems\__init__.py`

### `D:\EcodiaOS\systems\atune\__init__.py`

### `D:\EcodiaOS\systems\atune\core\__init__.py`

### `D:\EcodiaOS\systems\atune\core\salience\__init__.py`

### `D:\EcodiaOS\systems\atune\core\salience\atune_router.py`
**Functions**
- `_calculate_reward_from_unity(unity_result: Optional[Dict[str, Any]]) -> float`
- `_report_synapse_outcome(episode_id: str, task_key: str, metrics: dict) -> None`
- `_to_deliberation_spec(cfg: Dict[str, Any], summary_text: str, canonical: Dict[str, Any], salience_scores: Dict[str, Any], llm_analysis: Dict[str, Any]) -> DeliberationSpec`
- `atune_router(canonical: Dict[str, Any]) -> Dict[str, Any]`

### `D:\EcodiaOS\systems\atune\core\salience\embedding_salience_scoring.py`
**Functions**
- `cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float`
- `score_salience_from_embedding(canonical: dict, labels: list[str]) -> dict`

### `D:\EcodiaOS\systems\atune\core\salience\plan_next_steps.py`
**Functions**
- `_cluster_search_from_text(text: str, top_k: int = 3) -> List[Dict[str, Any]]`
- `_fetch_cluster_members(cluster_key: str, limit_per: int = 5) -> List[Dict[str, Any]]`
- `_prefetch_cluster_context(cluster_hits: List[Dict[str, Any]], max_clusters: int = 2, per_cluster: int = 5) -> Dict[str, Any]`
- `_ask_synapse_for_plan(summary: str, salience_scores: Dict[str, Any], canonical_event: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]`
- `plan_next_steps(summary: str, salience_scores: Dict[str, Any], canonical_event: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]`

### `D:\EcodiaOS\systems\atune\core\salience\routing_cache.py`

### `D:\EcodiaOS\systems\atune\core\salience\scorers.py`
**Functions**
- `_to_vec(arr: Any) -> np.ndarray`
- `cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float`
- `score_salience_from_embedding(canonical_event: Dict[str, Any], labels: List[str]) -> Dict[str, Dict[str, Any]]`

### `D:\EcodiaOS\systems\atune\core\salience\shared_nlp.py`
**Functions**
- `get_nlp()`

### `D:\EcodiaOS\systems\atune\core\salience\throttle_clustering.py`
**Functions**
- `mark_event_ingested() -> None`
- `should_run_clustering() -> bool`
- `mark_cluster_ran() -> None`

### `D:\EcodiaOS\systems\atune\core\salience\trigger_llm_analysis.py`
**Functions**
- `run_full_llm_analysis(canonical_event: Dict[str, Any], labels: List[str], embedding_scores: Dict[str, Any]) -> Dict[str, str]`
- `_one(label: str) -> tuple[str, str]`

### `D:\EcodiaOS\systems\atune\core\salience\numeric_analysis\z_score_outlier.py`
**Functions**
- `z_score_analysis(current: dict, past_window: list) -> float`

### `D:\EcodiaOS\systems\atune\core\salience\numeric_analysis\delta_compare.py`
**Functions**
- `delta_score(current: dict, past_window: list) -> float`

### `D:\EcodiaOS\systems\atune\core\salience\numeric_analysis\history_store.py`
**Functions**
- `init_db()`
- `store_event(source: str, event_type: str, payload: dict)`
- `get_recent_events(source: str, event_type: str, limit: int = 20) -> list[dict]`

### `D:\EcodiaOS\systems\atune\core\salience\numeric_analysis\scorer.py`
**Functions**
- `run_numeric_analysis(current_values: Dict[str, float], source: str, event_type: str) -> Dict[str, Any]`

### `D:\EcodiaOS\systems\atune\core\salience\numeric_analysis\trending_window.py`
**Functions**
- `trend_direction(current: dict, past_window: list) -> float`

### `D:\EcodiaOS\systems\atune\core\salience\numeric_analysis\volatility_window.py`
**Functions**
- `volatility_ratio(current: dict, past_window: list) -> float`

### `D:\EcodiaOS\systems\atune\core\utils\__init__.py`

### `D:\EcodiaOS\systems\axon\__init__.py`

### `D:\EcodiaOS\systems\axon\core\__init__.py`

### `D:\EcodiaOS\systems\axon\core\query_API\api_query.py`
**Functions**
- `google_headers()`
- `none_headers()`
- `query_any_api(key: str, custom_fields: dict = None) -> dict`

### `D:\EcodiaOS\systems\axon\core\query_API\api_runner.py`
**Functions**
- `resolve_dynamic_fields(payload: dict, offset_hours: int \| None = None) -> dict`
- `load_pull_timestamps()`
- `save_pull_timestamps(timestamps: dict)`
- `fetch_token(auth_type: str)`
- `tool_exists(key: str) -> bool`
- `ensure_tool_node(entry: dict)`
- `event_exists(text_hash: str) -> bool`
- `build_rss_event_payload(entry: dict, item: dict)`
- `build_api_event_payload(entry: dict, raw_data: dict)`
- `dispatch_event(event_payload: dict, key: str, source_id: str)`
- `fetch_and_send(entry: dict)`
- `main()`

### `D:\EcodiaOS\systems\axon\core\query_API\api_pull_registry.py`

### `D:\EcodiaOS\systems\contra\__init__.py`

### `D:\EcodiaOS\systems\contra\core\__init__.py`

### `D:\EcodiaOS\systems\contra\core\utils\__init__.py`

### `D:\EcodiaOS\systems\eido\__init__.py`

### `D:\EcodiaOS\systems\eido\core\__init__.py`

### `D:\EcodiaOS\systems\eido\core\utils\__init__.py`

### `D:\EcodiaOS\systems\ember\__init__.py`

### `D:\EcodiaOS\systems\ember\core\__init__.py`

### `D:\EcodiaOS\systems\ember\core\utils\__init__.py`

### `D:\EcodiaOS\systems\ethor\__init__.py`

### `D:\EcodiaOS\systems\ethor\core\__init__.py`

### `D:\EcodiaOS\systems\ethor\core\utils\__init__.py`

### `D:\EcodiaOS\systems\evo\__init__.py`

### `D:\EcodiaOS\systems\evo\core\__init__.py`

### `D:\EcodiaOS\systems\evo\core\EvoEngine\collect_conflict_data.py`
**Functions**
- `collect_conflict_data(days: int = 7, driver: Any = None) -> List[Dict[str, Any]]`

### `D:\EcodiaOS\systems\evo\core\EvoEngine\dao.py`
**Functions**
- `_load_json(p: Path) -> Any`
- `get_recent_codegen_feedback(limit: int = 10) -> List[Dict[str, Any]]`

### `D:\EcodiaOS\systems\evo\core\EvoEngine\engine.py`
**Classes**
- **EvoEngine**  bases: ``
  - `__init__(self, seed: Optional[int] = None)`
  - `_get_synapse_selection(self, state: EvoState) -> SelectArmResponse`
  - `_report_synapse_outcome(self, episode_id: str, candidate: ScoredCandidate)`
  - `run_experiment(self, spec: EvoSpec) -> EvoResult`
  - `step(self, state: EvoState) -> EvoResult`
**Functions**
- `__init__(self, seed: Optional[int] = None)`
- `_get_synapse_selection(self, state: EvoState) -> SelectArmResponse`
- `_report_synapse_outcome(self, episode_id: str, candidate: ScoredCandidate)`
- `run_experiment(self, spec: EvoSpec) -> EvoResult`
- `step(self, state: EvoState) -> EvoResult`

### `D:\EcodiaOS\systems\evo\core\EvoEngine\evolve_from_conflict.py`
**Classes**
- **EvoSession**  bases: ``
  - `__init__(self, context: Dict[str, Any])`
**Functions**
- `__init__(self, context: Dict[str, Any])`
- `_local_extractive_summary(text: str, max_sentences: int = 4, max_chars: int = 1200) -> str`
- `_normalize_prompt(description: str, insights: List[str]) -> List[Dict[str, Any]]`
- `extract_json_block(raw: str) -> Optional[str]`
- `_call_llm_for_decision(description: str, insights: List[str]) -> Dict[str, Any]`
- `_escalate_via_atune(description: str, insights: List[str], context: Dict[str, Any]) -> Dict[str, Any]`
- `_handle_deliberation(payload: Dict[str, Any], context: Dict[str, Any])`
- `_handle_ignore(payload: Dict[str, Any])`
- `_log_and_link_reflection(conflict_id: str, llm_decision: Dict[str, Any]) -> str`
- `evolve_from_conflict(conflict_id: str, description: str, insights: List[str], tags: List[str] = []) -> dict`

### `D:\EcodiaOS\systems\evo\core\EvoEngine\route_by_question_type.py`
**Functions**
- `route_conflict_questions(conflict_data: list[dict]) -> list[dict]`

### `D:\EcodiaOS\systems\evo\core\EvoEngine\create_frontend_questions.py`
**Functions**
- `log_evo_question(question: Dict[str, Any], conflict_id: str) -> str`
- `get_recent_conflict_nodes(days: int = 1) -> List[Dict[str, Any]] | Dict[str, str]`
- `create_frontend_questions() -> List[Dict[str, Any]]`

### `D:\EcodiaOS\systems\evo\core\EvoEngine\patrol.py`
**Functions**
- `run_evo_patrol()`

### `D:\EcodiaOS\systems\evo\core\EvoEngine\choices\analyze_choice_distribution.py`
**Functions**
- `process_choice_question(question_id: str, question_text: str, answers: List[Dict]) -> str`

### `D:\EcodiaOS\systems\evo\core\EvoEngine\sliders\aggregate_slider_data.py`
**Functions**
- `_format_stats(values: List[float]) -> str`
- `process_slider_question(question_id: str, question_text: str, answers: List[Dict]) -> str`

### `D:\EcodiaOS\systems\evo\core\EvoEngine\text\cluster_answers.py`
**Functions**
- `process_text_question(question_id: str, question_text: str, answers: List[Dict]) -> List[str]`

### `D:\EcodiaOS\systems\evo\core\EvoEngine\archivist\__init__.py`
**Classes**
- **Archivist**  bases: ``
  - `record_experiment(self, spec: Any) -> str`
  - `record_generation(self, parent_key: Optional[str], cand: Any, call_id: Optional[str], metrics: Dict[str, Any]) -> str`
**Functions**
- `record_experiment(self, spec: Any) -> str`
- `record_generation(self, parent_key: Optional[str], cand: Any, call_id: Optional[str], metrics: Dict[str, Any]) -> str`

### `D:\EcodiaOS\systems\evo\core\EvoEngine\selector\__init__.py`
**Classes**
- **Selector**  bases: ``
  - `__init__(self)`
  - `pick(self, scored: List[ScoredCandidate], policy: dict) -> List[ScoredCandidate]`
  - `_threshold_pick(self, scored: List[ScoredCandidate], policy: dict) -> List[ScoredCandidate]`
  - `_top_k_pick(self, scored: List[ScoredCandidate], policy: dict) -> List[ScoredCandidate]`
  - `_bandit_pick(self, scored: List[ScoredCandidate], policy: dict) -> List[ScoredCandidate]`
  - `log_bandit_reward(self, winners: List[ScoredCandidate])`
  - `evolve_bandit_strategies(self)`
  - `_find_merge_candidates(self, arms: List[dict]) -> List[Tuple[str, str]]`
  - `_find_split_candidates(self, arms: List[dict]) -> List[str]`
**Functions**
- `__init__(self)`
- `pick(self, scored: List[ScoredCandidate], policy: dict) -> List[ScoredCandidate]`
- `_threshold_pick(self, scored: List[ScoredCandidate], policy: dict) -> List[ScoredCandidate]`
- `_top_k_pick(self, scored: List[ScoredCandidate], policy: dict) -> List[ScoredCandidate]`
- `_bandit_pick(self, scored: List[ScoredCandidate], policy: dict) -> List[ScoredCandidate]`
- `log_bandit_reward(self, winners: List[ScoredCandidate])`
- `evolve_bandit_strategies(self)`
- `_find_merge_candidates(self, arms: List[dict]) -> List[Tuple[str, str]]`
- `_find_split_candidates(self, arms: List[dict]) -> List[str]`

### `D:\EcodiaOS\systems\evo\core\EvoEngine\scorer\__init__.py`
**Functions**
- `_load_weights_from_env() -> Optional[Dict[str, Dict[str, Any]]]`
- `_load_weights_from_graph() -> Optional[Dict[str, Dict[str, Any]]]`
- `_fetch() -> Optional[Dict[str, Dict[str, Any]]]`
- `_get_metric_config(metric_names: Tuple[str, ...]) -> Dict[str, Dict[str, Any]]`
- `_robust_z_to_unit(x: float, median: float, mad: float) -> float`
- `_summarize_scale(values: Dict[str, float], higher_is_better: bool) -> Tuple[float, float]`
- `fuse_metrics(baseline: Dict[str, float], custom: Dict[str, float], heuristics: Dict[str, float]) -> Dict[str, float]`

### `D:\EcodiaOS\systems\evo\core\EvoEngine\reporter\__init__.py`
**Classes**
- **Reporter**  bases: ``
  - `__init__(self) -> None`
  - `log_results(self, result: EvoResult) -> None`
  - `generate_summary(self, winners: List[ScoredCandidate]) -> str`
**Functions**
- `__init__(self) -> None`
- `log_results(self, result: EvoResult) -> None`
- `generate_summary(self, winners: List[ScoredCandidate]) -> str`

### `D:\EcodiaOS\systems\evo\core\EvoEngine\schemas\__init__.py`
**Classes**
- **EvoSpec** _(pydantic)_  bases: `BaseModel`
- **EvoState** _(pydantic)_  bases: `BaseModel`
- **ScoredCandidate** _(pydantic)_  bases: `BaseModel`
- **EvoResult** _(pydantic)_  bases: `BaseModel`
- **EvalReport** _(pydantic)_  bases: `BaseModel`

### `D:\EcodiaOS\systems\evo\core\EvoEngine\utils\__init__.py`

### `D:\EcodiaOS\systems\evo\core\EvoEngine\registry_sync\__init__.py`
**Classes**
- **RegistrySync**  bases: ``
  - `__init__(self, driver: Any = None)`
  - `upsert_tool(self, candidate_key: str, metrics: Dict[str, Any]) -> None`
**Functions**
- `__init__(self, driver: Any = None)`
- `upsert_tool(self, candidate_key: str, metrics: Dict[str, Any]) -> None`

### `D:\EcodiaOS\systems\evo\core\utils\__init__.py`

### `D:\EcodiaOS\systems\mythos\__init__.py`

### `D:\EcodiaOS\systems\mythos\core\__init__.py`

### `D:\EcodiaOS\systems\mythos\core\utils\__init__.py`

### `D:\EcodiaOS\systems\nova\__init__.py`

### `D:\EcodiaOS\systems\nova\core\__init__.py`

### `D:\EcodiaOS\systems\nova\core\nova_tool_orchestrator.py`
**Functions**
- `create_tool_from_reflection(driver: AsyncDriver, reflection_id: str, instructions: str)`

### `D:\EcodiaOS\systems\nova\core\nova_tool_planner.py`
**Functions**
- `plan_tool_from_reflection(evo_text: str, instructions: str, reflection_id: str) -> dict`

### `D:\EcodiaOS\systems\nova\core\nova_validators.py`
**Functions**
- `validate_code_output(output: Any, tool_metadata: Dict) -> Dict[str, Any]`

### `D:\EcodiaOS\systems\nova\core\utils\__init__.py`

### `D:\EcodiaOS\systems\qora\__init__.py`

### `D:\EcodiaOS\systems\qora\core\__init__.py`

### `D:\EcodiaOS\systems\qora\core\origin_ingest.py`
**Functions**
- `ensure_origin_indices() -> None`
- `_embed_for_node(title: str, summary: str, what: str) -> List[float]`
- `_embed_for_edge(from_title: str, rel_label: str, to_title: str, note: str) -> List[float]`
- `_has_origin_label(iid: int) -> bool`
- `force_origin_label(node_id: int) -> None`
- `_title_by_id(iid: int) -> str`
- `create_origin_node(contributor: str, title: str, summary: str, what: str, where: Optional[str], when: Optional[str], tags: List[str]) -> Tuple[str, int]`
- `resolve_event_or_internal_id(any_id: str) -> int`
- `create_edges_from(from_internal_id: int, edges: List[Dict[str, Any]]) -> int`
- `search_mixed(query: str, k: int = 10) -> List[Dict[str, Any]]`

### `D:\EcodiaOS\systems\qora\core\tools\__init__.py`

### `D:\EcodiaOS\systems\qora\core\utils\__init__.py`

### `D:\EcodiaOS\systems\qora\core\architecture\arch_patrol.py`
**Classes**
- **CodeParser**  bases: ``
  - `__init__(self, file_path: str, source_code: str)`
  - `_qualname(self, stack: List[ast.AST], node: ast.FunctionDef) -> str`
  - `parse(self) -> List[Dict[str, Any]]`
- **V**  bases: `ast.NodeVisitor`
  - `visit_ClassDef(self, node: ast.ClassDef)`
  - `visit_FunctionDef(self, node: ast.FunctionDef)`
**Functions**
- `_file_lang(path: str) -> str`
- `_sha256(path: str) -> str`
- `_count_loc(path: str) -> int`
- `__init__(self, file_path: str, source_code: str)`
- `_qualname(self, stack: List[ast.AST], node: ast.FunctionDef) -> str`
- `parse(self) -> List[Dict[str, Any]]`
- `visit_ClassDef(self, node: ast.ClassDef)`
- `visit_FunctionDef(self, node: ast.FunctionDef)`
- `get_function_uid(repo_name: str, file_rel_path: str, qualname: str) -> str`
- `upsert_artifacts_batch(rows: List[Dict[str, Any]]) -> None`
- `upsert_functions_batch(rows: List[Dict[str, Any]]) -> None`
- `_embedding_text(file_rel_path: str, fn: Dict[str, Any]) -> str`
- `crawl_and_ingest(root_path: str, repo_name: str, embed: bool = True)`

### `D:\EcodiaOS\systems\qora\core\architecture\arch_execution.py`
**Classes**
- **SystemFunctionDesc** _(dataclass)_  bases: ``
**Functions**
- `fetch_system_function(uid: str) -> Optional[SystemFunctionDesc]`
- `search_system_functions(query: str, limit: int = 5) -> List[SystemFunctionDesc]`
- `_module_from_file_path(file_path: str) -> str`
- `_resolve_attr_chain(root: Any, qualname: str) -> Any`
- `_ensure_syspath(repo_root: Optional[str]) -> None`
- `_safe_jsonish(x: Any, max_chars: int = 8000) -> Any`
- `_log_run(desc: SystemFunctionDesc, ok: bool, started: float, duration_ms: int, args: Dict[str, Any], result: Any, caller: Optional[str] = None) -> None`
- `execute_by_uid(uid: str, args: Dict[str, Any] \| None = None, repo_root: Optional[str] = None, log: bool = True, caller: Optional[str] = None) -> Any`
- `search_and_execute(query: str, args: Dict[str, Any] \| None = None, repo_root: Optional[str] = None, top_k: int = 1, log: bool = True, caller: Optional[str] = None) -> Any`

### `D:\EcodiaOS\systems\qora\core\immune\auto_instrument.py`
**Classes**
- **ConflictLogHandler**  bases: `logging.Handler`
  - `__init__(self, component: str = 'logger', version: Optional[str] = None)`
  - `emit(self, record: logging.LogRecord)`
**Functions**
- `_wrap_callable(fn, component: str, version: Optional[str], severity: str = 'medium')`
- `wrapped(*a, **kw)`
- `wrapped(*a, **kw)`
- `_instrument_class(cls, component: str, version: Optional[str], include_privates: bool)`
- `_instrument_module(mod: ModuleType, component: str, version: Optional[str], include_privates: bool)`
- `install_immune(driver: object \| None = None, include_packages: Sequence[str] = ('systems', 'core', 'services'), version: Optional[str] = None, include_privates: bool = False, exclude_predicate: Optional[Callable[[str], bool]] = None, component_resolver: Optional[Callable[[str], str]] = None)`
- `excepthook(etype, value, tb)`
- `thread_hook(args: threading.ExceptHookArgs)`
- `async_handler(loop, context)`
- `__init__(self, component: str = 'logger', version: Optional[str] = None)`
- `emit(self, record: logging.LogRecord)`

### `D:\EcodiaOS\systems\qora\core\immune\conflict_sdk.py`
**Functions**
- `_redact(d: Dict[str, Any]) -> Dict[str, Any]`
- `_normalize_stack(tb_list, depth: int = 6) -> str`
- `make_signature(exc: BaseException, component: str, version: str, extra: Dict[str, Any]) -> str`
- `log_conflict(exc: BaseException, component: str, severity: str = 'medium', version: Optional[str] = None, context: Optional[Dict[str, Any]] = None)`

### `D:\EcodiaOS\systems\qora\core\immune\conflict_ingestor.py`
**Functions**
- `on_conflict_detected(payload: Dict[str, Any])`

### `D:\EcodiaOS\systems\synk\__init__.py`

### `D:\EcodiaOS\systems\synk\api\__init__.py`

### `D:\EcodiaOS\systems\synk\core\__init__.py`

### `D:\EcodiaOS\systems\synk\core\tools\__init__.py`

### `D:\EcodiaOS\systems\synk\core\tools\cluster.py`
**Functions**
- `fetch_all_event_content(driver)`
- `get_clusters_from_gemini(event_data: list[dict])`
- `update_nodes_with_clusters(driver, clustered_data: list[dict])`
- `run_native_clustering_pipeline(driver = None, *_, **__)`

### `D:\EcodiaOS\systems\synk\core\tools\cluster_tools.py`
**Functions**
- `fetch_cluster_context_tool(driver_like: Any, context: Dict[str, Any], cluster_keys: List[str], per_cluster: int = 5, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]`

### `D:\EcodiaOS\systems\synk\core\tools\clusters.py`
**Functions**
- `_fetch_member_texts(member_ids: List[str]) -> List[str]`
- `_fetch_member_vectors(member_ids: List[str], prop: str = EVENT_PROP_VECTOR) -> np.ndarray`
- `_centroid(mat: np.ndarray) -> List[float]`
- `_summarize_texts(texts: List[str], max_chars: int = 4000) -> str`
- `ensure_cluster_vector_index(driver = None) -> None`
- `upsert_cluster(run_id: str, cluster_id: int, member_event_ids: List[str], model: str = 'gemini-2.5-pro', compute_summary: bool = True, driver = None) -> Dict`
- `link_members(run_id: str, cluster_key: str, member_event_ids: List[str], driver = None) -> None`
- `materialize_clusters_from_event_assignments(run_id: str, min_size: int = 1, driver = None, compute_summary: bool = True) -> Dict[int, Dict]`

### `D:\EcodiaOS\systems\synk\core\tools\mesa.py`
**Classes**
- **CustomModel**  bases: `Model`
  - `__init__(self)`
  - `step(self)`
**Functions**
- `create_agent_class(name, agent_fn)`
- `create_model(num_agents, agent_class, width = 10, height = 10)`
- `__init__(self)`
- `step(self)`
- `run_model(model, steps = 10)`
- `collect_agent_data(model)`

### `D:\EcodiaOS\systems\synk\core\tools\native_clustering.py`
**Functions**
- `fetch_event_vectors(prop: str = 'vector_gemini') -> Tuple[List[str], np.ndarray]`
- `fetch_all_event_content() -> List[Dict[str, str]]`
- `run_native_clustering_pipeline(k: Optional[int] = None, normalize: bool = True, max_concurrency: int = 8, update_batch_size: int = 1000) -> Dict`
- `_embed_one(text: str) -> List[float]`
- `embed_batch(items: List[Dict], max_concurrency: int = 8) -> np.ndarray`
- `choose_k(n: int, k: Optional[int] = None) -> int`
- `kmeans_numpy(x: np.ndarray, k: int, iters: int = 50, seed: int = 42) -> Tuple[np.ndarray, np.ndarray]`
- `try_sklearn_kmeans(x: np.ndarray, k: int) -> Optional[np.ndarray]`
- `update_nodes_with_clusters(event_ids: List[str], labels: np.ndarray, batch_size: int = 1000) -> None`

### `D:\EcodiaOS\systems\synk\core\tools\neo.py`
**Functions**
- `_safe_neo_props(props: Dict[str, Any]) -> Dict[str, Any]`
- `_safe(val)`
- `_get_or_make_event_id(properties: Dict[str, Any]) -> str`
- `add_relationship(src_match: Dict[str, Any], dst_match: Dict[str, Any], rel_type: str, rel_props: Optional[Dict[str, Any]] = None, intermediary: Optional[Dict[str, Any]] = None, dual_edges: bool = False)`
- `matcher_str(match_dict, prefix)`
- `_ensure_list(v: Any) -> Optional[List[float]]`
- `fetch_exemplar_embeddings(scorer: str, limit: int = 50, prefer: str = 'gemini', reembed_missing_gemini: bool = True) -> List[Dict[str, Any]]`
- `semantic_graph_search(query_text: str, top_k: int = 5, labels: Optional[List[str]] = None) -> List[Dict[str, Any]]`
- `add_node(labels: List[str], properties: Optional[Dict[str, Any]] = None, embed_text: Optional[str] = None) -> Dict[str, Any]`
- `create_conflict_node(system: str, description: str, origin_node_id: str, additional_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]`

### `D:\EcodiaOS\systems\synk\core\tools\schema_bootstrap.py`
**Functions**
- `_apply_all(queries: Iterable[str]) -> None`
- `_ensure_vector_indexes() -> None`
- `ensure_schema() -> None`
- `main() -> None`

### `D:\EcodiaOS\systems\synk\core\tools\vector_store.py`
**Functions**
- `_index_name(label: str, prop: str, dims: int, sim: str, name: Optional[str] = None) -> str`
- `_quote_ident(x: str) -> str`
- `create_vector_index(driver_like: Any = None, label: str = DEFAULT_LABEL, prop: str = DEFAULT_PROP, dims: int = DEFAULT_DIMS, sim: str = DEFAULT_SIM, name: Optional[str] = None, meta: Optional[Dict[str, Any]] = None) -> str`
- `embed_and_add_node_vector(driver_like: Any = None, text: str, node_id: str, id_property: str = 'event_id', prop: str = DEFAULT_PROP, dims: int = DEFAULT_DIMS, meta: Optional[Dict[str, Any]] = None) -> None`
- `search_vector_index(driver_like: Any = None, query_text: str = '', top_k: int = 5, label: str = DEFAULT_LABEL, prop: str = DEFAULT_PROP, dims: int = DEFAULT_DIMS, sim: str = DEFAULT_SIM, index_name: Optional[str] = None, ensure_index: bool = False, meta: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]`

### `D:\EcodiaOS\systems\synk\core\switchboard\client.py`
**Classes**
- **Switchboard**  bases: ``
  - `__init__(self, ttl_sec: int = 60)`
  - `_refresh(self, prefix: Optional[str] = None) -> None`
  - `get(self, key: str, default: Any = None) -> Any`
  - `get_bool(self, key: str, default: bool = False) -> bool`
  - `get_int(self, key: str, default: int = 0) -> int`
  - `get_float(self, key: str, default: float = 0.0) -> float`
**Functions**
- `__init__(self, ttl_sec: int = 60)`
- `_refresh(self, prefix: Optional[str] = None) -> None`
- `get(self, key: str, default: Any = None) -> Any`
- `get_bool(self, key: str, default: bool = False) -> bool`
- `get_int(self, key: str, default: int = 0) -> int`
- `get_float(self, key: str, default: float = 0.0) -> float`

### `D:\EcodiaOS\systems\synk\core\switchboard\runtime.py`

### `D:\EcodiaOS\systems\synk\core\switchboard\flag_deps.py`
**Functions**
- `require_flag_true(key: str, default: bool = False)`
- `_dep()`

### `D:\EcodiaOS\systems\synk\core\switchboard\gatekit.py`
**Functions**
- `gate(flag_key: str, default: bool = False) -> bool`
- `route_gate(flag_key: str, default: bool = False, status_code: int = 403, detail: Optional[str] = None)`
- `_dep()`
- `gated_async(flag_key: str, default: bool = False, ret: Any = None)`
- `deco(fn)`
- `wrapper(*a, **kw)`
- `gated_sync(flag_key: str, default: bool = False, ret: Any = None)`
- `deco(fn)`
- `wrapper(*a, **kw)`
- `_check()`
- `gated_loop(task_coro: Callable[[], Awaitable[Any]], enabled_key: str, interval_key: Optional[str] = None, default_interval: int = 60, jitter: float = 0.0)`

### `D:\EcodiaOS\systems\synk\core\switchboard\__init__.py`

### `D:\EcodiaOS\systems\thread\__init__.py`

### `D:\EcodiaOS\systems\thread\core\identity_shift.py`
**Functions**
- `_safe_label(raw: str) -> str`
- `_embed_text_3072(text: str) -> Optional[list[float]]`
- `evaluate_identity_shift_thread(session: Any, m_event_id: str) -> None`

### `D:\EcodiaOS\systems\thread\core\identity_shift_prompts.py`
**Functions**
- `build_identity_shift_prompt(mevent_data: dict) -> tuple[str, str]`

### `D:\EcodiaOS\systems\unity\__init__.py`

### `D:\EcodiaOS\systems\unity\schemas.py`
**Classes**
- **InputRef** _(pydantic)_  bases: `BaseModel`
- **DeliberationSpec** _(pydantic)_  bases: `BaseModel`
- **VerdictModel** _(pydantic)_  bases: `BaseModel`
- **DeliberationResponse** _(pydantic)_  bases: `BaseModel`
- **MetaCriticismProposalEvent** _(pydantic)_  bases: `BaseModel`
- **RoomConfiguration** _(pydantic)_  bases: `BaseModel`
- **FederatedConsensusRequest** _(pydantic)_  bases: `BaseModel`
- **FederatedConsensusResponse** _(pydantic)_  bases: `BaseModel`
- **Cognit** _(pydantic)_  bases: `BaseModel`
- **BroadcastEvent** _(pydantic)_  bases: `BaseModel`

### `D:\EcodiaOS\systems\unity\core\__init__.py`

### `D:\EcodiaOS\systems\unity\core\neo\graph_writes.py`
**Functions**
- `create_deliberation_node(episode_id: str, spec: DeliberationSpec, rcu_start_ref: str) -> str`
- `record_transcript_chunk(deliberation_id: str, turn: int, role: str, content: str) -> str`
- `upsert_claim(deliberation_id: str, claim_text: str, created_by_role: str) -> str`
- `link_support_or_attack(from_node_id: str, from_node_label: str, to_node_id: str, to_node_label: str, rel_type: str, rationale: str) -> str`
- `finalize_verdict(deliberation_id: str, verdict: VerdictModel, rcu_end_ref: str) -> str`

### `D:\EcodiaOS\systems\unity\core\room\adjudicator.py`
**Classes**
- **Adjudicator**  bases: ``
  - `__new__(cls)`
  - `_get_applicable_rules(self, constraints: List[str]) -> List[Dict[str, Any]]`
  - `_bayesian_aggregation(self, participant_beliefs: Dict[str, float], calibration_priors: Dict[str, float]) -> Tuple[float, float]`
  - `decide(self, participant_beliefs: Dict[str, float], calibration_priors: Dict[str, float], spec_constraints: List[str]) -> VerdictModel`
**Functions**
- `__new__(cls)`
- `_get_applicable_rules(self, constraints: List[str]) -> List[Dict[str, Any]]`
- `_bayesian_aggregation(self, participant_beliefs: Dict[str, float], calibration_priors: Dict[str, float]) -> Tuple[float, float]`
- `decide(self, participant_beliefs: Dict[str, float], calibration_priors: Dict[str, float], spec_constraints: List[str]) -> VerdictModel`

### `D:\EcodiaOS\systems\unity\core\room\orchestrator.py`
**Classes**
- **DeliberationManager**  bases: ``
  - `__new__(cls)`
  - `handle_ignition_event(self, broadcast: Dict[str, Any])`
  - `run_session(self, spec: DeliberationSpec) -> Dict[str, Any]`
**Functions**
- `__new__(cls)`
- `handle_ignition_event(self, broadcast: Dict[str, Any])`
- `run_session(self, spec: DeliberationSpec) -> Dict[str, Any]`

### `D:\EcodiaOS\systems\unity\core\room\participants.py`
**Classes**
- **ParticipantRegistry**  bases: ``
  - `__new__(cls)`
  - `get_role_info(self, role_name: str) -> Dict[str, Any]`
  - `list_roles(self) -> list[str]`
**Functions**
- `__new__(cls)`
- `get_role_info(self, role_name: str) -> Dict[str, Any]`
- `list_roles(self) -> list[str]`

### `D:\EcodiaOS\systems\unity\core\room\argument_map.py`
**Classes**
- **ArgumentMiner**  bases: ``
  - `__init__(self)`
  - `add_claim(self, claim_id: str, text: str)`
  - `_ensure_node(self, claim_id: str)`
  - `add_inference(self, from_claim_id: str, to_claim_id: str, rel_type: str)`
  - `_support_ancestry(self, conclusion_id: str) -> Set[str]`
  - `_collect_base_leaves(self, ancestry: Set[str]) -> Set[str]`
  - `_defended_filter(self, leaves: Set[str], ancestry: Set[str]) -> Set[str]`
  - `get_minimal_assumption_set(self, conclusion_id: str) -> Set[str]`
**Functions**
- `__init__(self)`
- `add_claim(self, claim_id: str, text: str)`
- `_ensure_node(self, claim_id: str)`
- `add_inference(self, from_claim_id: str, to_claim_id: str, rel_type: str)`
- `_support_ancestry(self, conclusion_id: str) -> Set[str]`
- `_collect_base_leaves(self, ancestry: Set[str]) -> Set[str]`
- `_defended_filter(self, leaves: Set[str], ancestry: Set[str]) -> Set[str]`
- `get_minimal_assumption_set(self, conclusion_id: str) -> Set[str]`

### `D:\EcodiaOS\systems\unity\core\protocols\debate.py`
**Classes**
- **DebateProtocol**  bases: ``
  - `__init__(self, spec: DeliberationSpec, deliberation_id: str, episode_id: str)`
  - `_add_transcript(self, role: str, content: str) -> None`
  - `_generate_participant_response(self, role: str, current_transcript: str) -> str`
  - `run(self) -> VerdictModel`
**Functions**
- `_truncate(text: str, limit: int = _MAX_TRANSCRIPT_CHARS) -> str`
- `_extract_response_text(resp: Any, fallback: str) -> str`
- `__init__(self, spec: DeliberationSpec, deliberation_id: str, episode_id: str)`
- `_add_transcript(self, role: str, content: str) -> None`
- `_generate_participant_response(self, role: str, current_transcript: str) -> str`
- `run(self) -> VerdictModel`

### `D:\EcodiaOS\systems\unity\core\protocols\critique_and_repair.py`
**Classes**
- **ProtocolState**  bases: `Enum`
- **CritiqueAndRepairProtocol**  bases: ``
  - `__init__(self, spec: DeliberationSpec, deliberation_id: str, episode_id: str, panel: list[str])`
  - `_add_transcript(self, role: str, content: str)`
  - `_run_state_propose(self)`
  - `_run_state_critique(self)`
  - `_run_state_repair(self)`
  - `_run_state_cross_exam(self)`
  - `_run_state_adjudicate(self) -> VerdictModel`
  - `run(self) -> VerdictModel`
**Functions**
- `__init__(self, spec: DeliberationSpec, deliberation_id: str, episode_id: str, panel: list[str])`
- `_add_transcript(self, role: str, content: str)`
- `_run_state_propose(self)`
- `_run_state_critique(self)`
- `_run_state_repair(self)`
- `_run_state_cross_exam(self)`
- `_run_state_adjudicate(self) -> VerdictModel`
- `run(self) -> VerdictModel`

### `D:\EcodiaOS\systems\unity\core\protocols\argument_mining.py`
**Classes**
- **ArgumentMiningProtocol**  bases: ``
  - `__init__(self, spec: DeliberationSpec, deliberation_id: str, episode_id: str)`
  - `_add_transcript(self, role: str, content: str)`
  - `run(self) -> VerdictModel`
**Functions**
- `__init__(self, spec: DeliberationSpec, deliberation_id: str, episode_id: str)`
- `_add_transcript(self, role: str, content: str)`
- `run(self) -> VerdictModel`

### `D:\EcodiaOS\systems\unity\core\protocols\meta_criticism.py`
**Classes**
- **MetaCriticismProtocol**  bases: ``
  - `__init__(self, spec: DeliberationSpec, deliberation_id: str, episode_id: str)`
  - `_add_transcript(self, role: str, content: str)`
  - `_fetch_deliberation(self, delib_id: str) -> Dict[str, Any]`
  - `_measure_efficiency(transcript: List[Dict[str, Any]], verdict: Dict[str, Any]) -> Dict[str, Any]`
  - `_build_proposal(self, source_delib_id: str, diag: Dict[str, Any]) -> MetaCriticismProposalEvent`
  - `run(self) -> VerdictModel`
**Functions**
- `__init__(self, spec: DeliberationSpec, deliberation_id: str, episode_id: str)`
- `_add_transcript(self, role: str, content: str)`
- `_fetch_deliberation(self, delib_id: str) -> Dict[str, Any]`
- `_measure_efficiency(transcript: List[Dict[str, Any]], verdict: Dict[str, Any]) -> Dict[str, Any]`
- `_build_proposal(self, source_delib_id: str, diag: Dict[str, Any]) -> MetaCriticismProposalEvent`
- `run(self) -> VerdictModel`

### `D:\EcodiaOS\systems\unity\core\protocols\federated_consensus.py`
**Classes**
- **FederatedConsensusProtocol**  bases: ``
  - `__init__(self, base_spec: DeliberationSpec, room_configs: List[RoomConfiguration], quorum_threshold: float)`
  - `_run_single_room(self, config: RoomConfiguration) -> VerdictModel`
  - `run(self) -> Dict[str, Any]`
**Functions**
- `_to_verdict(obj: Any) -> VerdictModel`
- `_weighted_aggregate(verdicts: List[VerdictModel]) -> Tuple[float, float, float]`
- `__init__(self, base_spec: DeliberationSpec, room_configs: List[RoomConfiguration], quorum_threshold: float)`
- `_run_single_room(self, config: RoomConfiguration) -> VerdictModel`
- `run(self) -> Dict[str, Any]`
- `guarded_run(cfg: RoomConfiguration) -> VerdictModel`

### `D:\EcodiaOS\systems\unity\core\protocols\concurrent_competition.py`
**Classes**
- **ConcurrentCompetitionProtocol**  bases: ``
  - `__init__(self, spec: DeliberationSpec, deliberation_id: str, episode_id: str, panel: List[str])`
  - `_sub_process(self, role: str, stop_event: asyncio.Event)`
  - `run(self) -> VerdictModel`
**Functions**
- `__init__(self, spec: DeliberationSpec, deliberation_id: str, episode_id: str, panel: List[str])`
- `_sub_process(self, role: str, stop_event: asyncio.Event)`
- `run(self) -> VerdictModel`

### `D:\EcodiaOS\systems\unity\core\workspace\global_workspace.py`
**Classes**
- **AttentionMechanism**  bases: ``
  - `__init__(self) -> None`
  - `select_for_broadcast(self, cognits: List[Cognit]) -> Optional[Cognit]`
- **GlobalWorkspace**  bases: ``
  - `__new__(cls)`
  - `handle_qualia_event(self, qualia_state: Dict[str, Any]) -> None`
  - `post_cognit(self, source_process: str, content: str, salience: float, is_internal: bool = False) -> None`
  - `run_broadcast_cycle(self) -> None`
**Functions**
- `__init__(self) -> None`
- `select_for_broadcast(self, cognits: List[Cognit]) -> Optional[Cognit]`
- `__new__(cls)`
- `handle_qualia_event(self, qualia_state: Dict[str, Any]) -> None`
- `post_cognit(self, source_process: str, content: str, salience: float, is_internal: bool = False) -> None`
- `run_broadcast_cycle(self) -> None`

### `D:\EcodiaOS\systems\unity\core\t_o_m\modeler.py`
**Classes**
- **TheoryOfMindEngine**  bases: ``
  - `__new__(cls)`
  - `_load_role_model(self, role: str) -> Optional[Dict[str, Any]]`
  - `_ensure_model(self, role: str) -> Optional[Dict[str, Any]]`
  - `_last_token_from_state(state: Dict[str, Any]) -> str`
  - `_unigram_top(unigram: List[float], vocab: List[str], k: int = 5) -> List[Tuple[str, float]]`
  - `_predict_token_topk(self, role_model: Dict[str, Any], prev_token: str, k: int = 5) -> List[Tuple[str, float]]`
  - `_compose_argument(self, role: str, topic: str, keywords: List[str]) -> str`
  - `predict_argument(self, role: str, current_debate_state: Dict[str, Any]) -> str`
**Functions**
- `_tok(text: str) -> List[str]`
- `_clean_keywords(tokens: List[Tuple[str, float]], k: int = 5) -> List[str]`
- `__new__(cls)`
- `_load_role_model(self, role: str) -> Optional[Dict[str, Any]]`
- `_ensure_model(self, role: str) -> Optional[Dict[str, Any]]`
- `_last_token_from_state(state: Dict[str, Any]) -> str`
- `_unigram_top(unigram: List[float], vocab: List[str], k: int = 5) -> List[Tuple[str, float]]`
- `_predict_token_topk(self, role_model: Dict[str, Any], prev_token: str, k: int = 5) -> List[Tuple[str, float]]`
- `_compose_argument(self, role: str, topic: str, keywords: List[str]) -> str`
- `predict_argument(self, role: str, current_debate_state: Dict[str, Any]) -> str`

### `D:\EcodiaOS\systems\voxis\__init__.py`

### `D:\EcodiaOS\systems\voxis\core\__init__.py`

### `D:\EcodiaOS\systems\voxis\core\voxis_pipeline.py`
**Classes**
- **VoxisPipeline**  bases: ``
  - `__init__(self, user_input: str, user_id: str, phrase_event_id: str)`
  - `scoped_semantic_search(self, query_text: str, top_k: int = 5) -> List[Dict[str, Any]]`
  - `run(self) -> str`
  - `_build_stage1_prompt(self, userstate_context, identitystate_context) -> str`
  - `_build_stage2_prompt(self, sem_results, id_results, constellation_results, userstate_context, tate_mode) -> str`
  - `_parse_tool_queries(self, raw: str) -> Dict[str, str]`
  - `_apply_censorship(self, text: str) -> str`
  - `_get_userstate_embedding_context(self, top_k: int = 3) -> List[Dict[str, Any]]`
  - `soulphrase_constellation_search(self, query_text: str, top_k: int = 3) -> List[Dict[str, Any]]`
  - `_is_tate_mode(self) -> bool`
  - `_log_exchange(self, response_text: str, tate_mode: bool) -> None`
**Functions**
- `log(*args, **kwargs)`
- `convert_dates(obj)`
- `identitystate_search(query_text: str, top_k: int = 7) -> List[Dict[str, Any]]`
- `get_recent_identitystates(top_k: int = 10) -> List[Dict[str, Any]]`
- `__init__(self, user_input: str, user_id: str, phrase_event_id: str)`
- `scoped_semantic_search(self, query_text: str, top_k: int = 5) -> List[Dict[str, Any]]`
- `run(self) -> str`
- `_build_stage1_prompt(self, userstate_context, identitystate_context) -> str`
- `_build_stage2_prompt(self, sem_results, id_results, constellation_results, userstate_context, tate_mode) -> str`
- `_parse_tool_queries(self, raw: str) -> Dict[str, str]`
- `_apply_censorship(self, text: str) -> str`
- `_get_userstate_embedding_context(self, top_k: int = 3) -> List[Dict[str, Any]]`
- `soulphrase_constellation_search(self, query_text: str, top_k: int = 3) -> List[Dict[str, Any]]`
- `_is_tate_mode(self) -> bool`
- `_log_exchange(self, response_text: str, tate_mode: bool) -> None`

### `D:\EcodiaOS\systems\voxis\core\utils\__init__.py`

### `D:\EcodiaOS\systems\equor\__init__.py`

### `D:\EcodiaOS\systems\equor\schemas.py`
**Classes**
- **Facet** _(pydantic)_  bases: `BaseModel`
- **ConstitutionRule** _(pydantic)_  bases: `BaseModel`
- **Profile** _(pydantic)_  bases: `BaseModel`
- **ComposeRequest** _(pydantic)_  bases: `BaseModel`
- **ComposeResponse** _(pydantic)_  bases: `BaseModel`
- **Attestation** _(pydantic)_  bases: `BaseModel`
- **DriftReport** _(pydantic)_  bases: `BaseModel`
- **PatchProposalEvent** _(pydantic)_  bases: `BaseModel`
- **Invariant** _(pydantic)_  bases: `BaseModel`
- **InvariantCheckResult** _(pydantic)_  bases: `BaseModel`
- **InternalStateMetrics** _(pydantic)_  bases: `BaseModel`
- **QualiaState** _(pydantic)_  bases: `BaseModel`

### `D:\EcodiaOS\systems\equor\core\neo\graph_writes.py`
**Functions**
- `get_active_profile(agent: str, profile_name: str) -> Optional[Dict[str, Any]]`
- `get_nodes_by_ids(node_ids: List[str]) -> List[Dict[str, Any]]`
- `save_prompt_patch(response: ComposeResponse, request: ComposeRequest) -> str`
- `save_attestation(attestation: Attestation) -> str`
- `upsert_rules(rules: List[ConstitutionRule]) -> List[str]`
- `upsert_facet(facet: Facet) -> str`
- `upsert_profile(profile: Profile) -> str`
- `save_qualia_state(state: QualiaState) -> str`

### `D:\EcodiaOS\systems\equor\core\identity\constitution.py`
**Classes**
- **ConstitutionConflictError**  bases: `Exception`
  - `__init__(self, message: str, conflicting_rules: List[Dict[str, Any]])`
- **PredicateUnsatisfiedError**  bases: `Exception`
  - `__init__(self, message: str, failing_rule: Dict[str, Any])`
- **ConstitutionService**  bases: ``
  - `__new__(cls)`
  - `_evaluate_predicate(self, predicate: str, context: Dict[str, Any]) -> bool`
  - `check_formal_guards(self, rules: List[Dict[str, Any]], context: Dict[str, Any])`
  - `apply_precedence(self, rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]`
  - `check_for_conflicts(self, rules: List[Dict[str, Any]]) -> None`
**Functions**
- `__init__(self, message: str, conflicting_rules: List[Dict[str, Any]])`
- `__init__(self, message: str, failing_rule: Dict[str, Any])`
- `__new__(cls)`
- `_evaluate_predicate(self, predicate: str, context: Dict[str, Any]) -> bool`
- `check_formal_guards(self, rules: List[Dict[str, Any]], context: Dict[str, Any])`
- `apply_precedence(self, rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]`
- `check_for_conflicts(self, rules: List[Dict[str, Any]]) -> None`

### `D:\EcodiaOS\systems\equor\core\identity\registry.py`
**Classes**
- **RegistryError**  bases: `Exception`
- **IdentityRegistry**  bases: ``
  - `__new__(cls)`
  - `get_active_components_for_profile(self, agent: str, profile_name: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]`
**Functions**
- `_ensure_list(x: Any) -> List[Any]`
- `_dedupe_preserve_order(seq: Iterable[Any]) -> List[Any]`
- `_node_id(n: Dict[str, Any]) -> Optional[str]`
- `_has_label(n: Dict[str, Any], label: str) -> bool`
- `__new__(cls)`
- `get_active_components_for_profile(self, agent: str, profile_name: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]`

### `D:\EcodiaOS\systems\equor\core\identity\composer.py`
**Classes**
- **CompositionError**  bases: `Exception`
- **PromptComposer**  bases: ``
  - `__new__(cls)`
  - `_format_patch_text(self, facets: List[Dict[str, Any]], rules: List[Dict[str, Any]], warnings: List[str] = []) -> str`
  - `compose(self, request: ComposeRequest, rcu_ref: str) -> ComposeResponse`
**Functions**
- `__new__(cls)`
- `_format_patch_text(self, facets: List[Dict[str, Any]], rules: List[Dict[str, Any]], warnings: List[str] = []) -> str`
- `compose(self, request: ComposeRequest, rcu_ref: str) -> ComposeResponse`

### `D:\EcodiaOS\systems\equor\core\identity\homeostasis.py`
**Classes**
- **HomeostasisMonitor**  bases: ``
  - `__new__(cls)`
  - `get_monitor_for_agent(self, agent_name: str) -> 'AgentMonitor'`
  - `process_attestation(self, attestation: Attestation)`
  - `run_monitor_cycle(self)`
- **AgentMonitor**  bases: ``
  - `__init__(self, agent_name: str, composer: PromptComposer, window_size: int = 50, alert_threshold: float = _ALERT_THRESHOLD)`
  - `update_metrics(self, attestation: Attestation)`
  - `should_alert(self) -> bool`
  - `reset_alert_trigger(self)`
  - `generate_report(self) -> DriftReport`
  - `propose_tightened_patch(self, report: DriftReport)`
  - `_calculate_coverage(self, attestation: Attestation) -> Dict[str, Any]`
**Functions**
- `__new__(cls)`
- `get_monitor_for_agent(self, agent_name: str) -> 'AgentMonitor'`
- `process_attestation(self, attestation: Attestation)`
- `run_monitor_cycle(self)`
- `__init__(self, agent_name: str, composer: PromptComposer, window_size: int = 50, alert_threshold: float = _ALERT_THRESHOLD)`
- `update_metrics(self, attestation: Attestation)`
- `should_alert(self) -> bool`
- `reset_alert_trigger(self)`
- `generate_report(self) -> DriftReport`
- `propose_tightened_patch(self, report: DriftReport)`
- `_calculate_coverage(self, attestation: Attestation) -> Dict[str, Any]`

### `D:\EcodiaOS\systems\equor\core\identity\invariants.py`
**Classes**
- **InvariantAuditor**  bases: ``
  - `__new__(cls)`
  - `initialize(self)`
  - `run_audit(self) -> List[InvariantCheckResult]`
**Functions**
- `__new__(cls)`
- `initialize(self)`
- `run_audit(self) -> List[InvariantCheckResult]`

### `D:\EcodiaOS\systems\equor\core\qualia\manifold.py`
**Classes**
- **_AEWeights** _(dataclass)_  bases: ``
  - `to_npz(self, path: str \| Path) -> None`
  - `from_npz(path: str \| Path) -> '_AEWeights'`
- **TrainedAutoencoder**  bases: ``
  - `__init__(self, input_dim: int = 4, latent_dim: int = 2, eta0: float = 0.15)`
  - `save_weights(self, path: str \| Path) -> None`
  - `load_weights(self, path: str \| Path) -> None`
  - `_std(self) -> np.ndarray`
  - `_standardize(self, x: np.ndarray) -> np.ndarray`
  - `_update_stats(self, x: np.ndarray) -> None`
  - `_eta(self) -> float`
  - `encode(self, metrics_vector: np.ndarray) -> np.ndarray`
  - `update(self, metrics_vector: np.ndarray) -> None`
- **QualiaManifold**  bases: ``
  - `__new__(cls)`
  - `_init_model(self) -> None`
  - `get_model(self) -> TrainedAutoencoder`
  - `load_model_weights(self, path: str) -> None`
  - `process_metrics(self, metrics: InternalStateMetrics) -> QualiaState`
- **StateLogger**  bases: ``
  - `__new__(cls)`
  - `log_state(self, metrics: InternalStateMetrics) -> None`
**Functions**
- `to_npz(self, path: str \| Path) -> None`
- `from_npz(path: str \| Path) -> '_AEWeights'`
- `__init__(self, input_dim: int = 4, latent_dim: int = 2, eta0: float = 0.15)`
- `save_weights(self, path: str \| Path) -> None`
- `load_weights(self, path: str \| Path) -> None`
- `_std(self) -> np.ndarray`
- `_standardize(self, x: np.ndarray) -> np.ndarray`
- `_update_stats(self, x: np.ndarray) -> None`
- `_eta(self) -> float`
- `encode(self, metrics_vector: np.ndarray) -> np.ndarray`
- `update(self, metrics_vector: np.ndarray) -> None`
- `__new__(cls)`
- `_init_model(self) -> None`
- `get_model(self) -> TrainedAutoencoder`
- `load_model_weights(self, path: str) -> None`
- `process_metrics(self, metrics: InternalStateMetrics) -> QualiaState`
- `__new__(cls)`
- `log_state(self, metrics: InternalStateMetrics) -> None`

### `D:\EcodiaOS\systems\equor\core\qualia\trainer.py`
**Classes**
- **AutoencoderTrainer**  bases: ``
  - `__init__(self, model)`
  - `_prime_stats(self, X: np.ndarray) -> None`
  - `_epoch_loss(self, X: np.ndarray) -> float`
  - `train(self, data: np.ndarray, epochs: int = 10, shuffle: bool = True) -> Dict[str, Any]`
  - `save_weights(self, path: str \| Path) -> None`
- **ManifoldTrainer**  bases: ``
  - `__new__(cls)`
  - `_fetch_training_data(self) -> np.ndarray`
  - `run_training_cycle(self, min_samples: int = 16, epochs: int = 10) -> Dict[str, Any]`
**Functions**
- `_models_dir() -> Path`
- `_artifact_paths() -> Tuple[Path, Path]`
- `_std_from(model) -> np.ndarray`
- `_reconstruct(model, x: np.ndarray) -> np.ndarray`
- `__init__(self, model)`
- `_prime_stats(self, X: np.ndarray) -> None`
- `_epoch_loss(self, X: np.ndarray) -> float`
- `train(self, data: np.ndarray, epochs: int = 10, shuffle: bool = True) -> Dict[str, Any]`
- `save_weights(self, path: str \| Path) -> None`
- `__new__(cls)`
- `_fetch_training_data(self) -> np.ndarray`
- `run_training_cycle(self, min_samples: int = 16, epochs: int = 10) -> Dict[str, Any]`

### `D:\EcodiaOS\systems\equor\core\self\predictor.py`
**Classes**
- **SelfModel**  bases: ``
  - `__new__(cls)`
  - `_try_synapse_predict(self, current_qualia_coordinates: List[float], task_context: Dict[str, Any]) -> Optional[List[float]]`
  - `_estimate_from_history(self, current_qualia_coordinates: List[float], task_context: Dict[str, Any], limit: int = 1000) -> Optional[List[float]]`
  - `predict_next_state(self, current_qualia_coordinates: List[float], task_context: Dict[str, Any]) -> List[float]`
**Functions**
- `__new__(cls)`
- `_try_synapse_predict(self, current_qualia_coordinates: List[float], task_context: Dict[str, Any]) -> Optional[List[float]]`
- `_estimate_from_history(self, current_qualia_coordinates: List[float], task_context: Dict[str, Any], limit: int = 1000) -> Optional[List[float]]`
- `_pairs_where(where_clause: str) -> str`
- `predict_next_state(self, current_qualia_coordinates: List[float], task_context: Dict[str, Any]) -> List[float]`

### `D:\EcodiaOS\systems\synapse\schemas.py`
**Classes**
- **TaskContext** _(pydantic)_  bases: `BaseModel`
- **Config**  bases: ``
- **Candidate** _(pydantic)_  bases: `BaseModel`
- **SelectArmRequest** _(pydantic)_  bases: `BaseModel`
- **ArmScore** _(pydantic)_  bases: `BaseModel`
- **SelectArmResponse** _(pydantic)_  bases: `BaseModel`
- **SimulateRequest** _(pydantic)_  bases: `BaseModel`
- **SimulateResponse** _(pydantic)_  bases: `BaseModel`
- **SMTCheckRequest** _(pydantic)_  bases: `BaseModel`
- **SMTCheckResponse** _(pydantic)_  bases: `BaseModel`
- **BudgetResponse** _(pydantic)_  bases: `BaseModel`
- **ExplainRequest** _(pydantic)_  bases: `BaseModel`
- **ExplainResponse** _(pydantic)_  bases: `BaseModel`
- **LogOutcomeRequest** _(pydantic)_  bases: `BaseModel`
- **LogOutcomeResponse** _(pydantic)_  bases: `BaseModel`
- **PreferenceIngest** _(pydantic)_  bases: `BaseModel`
- **ContinueRequest** _(pydantic)_  bases: `BaseModel`
- **ContinueResponse** _(pydantic)_  bases: `BaseModel`
- **RepairRequest** _(pydantic)_  bases: `BaseModel`
- **RepairResponse** _(pydantic)_  bases: `BaseModel`
- **EpisodeSummary** _(pydantic)_  bases: `BaseModel`
- **ComparisonPairResponse** _(pydantic)_  bases: `BaseModel`
- **SubmitPreferenceRequest** _(pydantic)_  bases: `BaseModel`
- **PatchProposal** _(pydantic)_  bases: `BaseModel`

### `D:\EcodiaOS\systems\synapse\daemon.py`
**Functions**
- `run_synapse_autonomous_loops()`

### `D:\EcodiaOS\systems\synapse\core\__init__.py`

### `D:\EcodiaOS\systems\synapse\core\registry.py`
**Classes**
- **PolicyArm**  bases: ``
  - `__init__(self, arm_id: str, policy_graph: PolicyGraph, mode: str, bandit_head: NeuralLinearBanditHead)`
  - `is_safe_fallback(self) -> bool`
- **ArmRegistry**  bases: ``
  - `__new__(cls)`
  - `__init__(self)`
  - `initialize(self) -> None`
  - `reload(self) -> None`
  - `get_arm(self, arm_id: str) -> Optional[PolicyArm]`
  - `get_arms_for_mode(self, mode: str) -> List[PolicyArm]`
  - `list_arms_for_mode(self, mode: str) -> List[PolicyArm]`
  - `list_modes(self) -> List[str]`
  - `all_arm_ids(self) -> List[str]`
  - `add_arm(self, *args, **kwargs) -> None`
  - `get_safe_fallback_arm(self, mode: Optional[str] = None) -> PolicyArm`
  - `ensure_cold_start(self, min_modes: Iterable[str] = ('planful', 'greedy')) -> None`
**Functions**
- `_coerce_policy_graph(pg_like: Any) -> PolicyGraph`
- `_node_effects_says_dangerous(node: Any) -> bool`
- `_maybe_await(v)`
- `_default_llm_model() -> str`
- `_noop_pg_dict(arm_id: str) -> Dict[str, Any]`
- `__init__(self, arm_id: str, policy_graph: PolicyGraph, mode: str, bandit_head: NeuralLinearBanditHead)`
- `is_safe_fallback(self) -> bool`
- `__new__(cls)`
- `__init__(self)`
- `initialize(self) -> None`
- `reload(self) -> None`
- `get_arm(self, arm_id: str) -> Optional[PolicyArm]`
- `get_arms_for_mode(self, mode: str) -> List[PolicyArm]`
- `list_arms_for_mode(self, mode: str) -> List[PolicyArm]`
- `list_modes(self) -> List[str]`
- `all_arm_ids(self) -> List[str]`
- `add_arm(self, *args, **kwargs) -> None`
- `get_safe_fallback_arm(self, mode: Optional[str] = None) -> PolicyArm`
- `ensure_cold_start(self, min_modes: Iterable[str] = ('planful', 'greedy')) -> None`

### `D:\EcodiaOS\systems\synapse\core\tactics.py`
**Classes**
- **TacticalManager**  bases: ``
  - `__new__(cls)`
  - `_candidate_ids_from_request(self, req: SelectArmRequest) -> List[str]`
  - `_build_candidate_set(self, all_arms_in_mode: List[PolicyArm], x_vec: np.ndarray, req: SelectArmRequest, mode: str) -> List[PolicyArm]`
  - `_score_candidates(self, candidates: Iterable[PolicyArm], x_vec: np.ndarray) -> Dict[str, float]`
  - `select_arm(self, request: SelectArmRequest, mode: str) -> Tuple[PolicyArm, Dict[str, float]]`
  - `update(self, arm_id: str, reward: float) -> None`
  - `get_last_scores_for_arm(self, arm_id: str) -> Optional[Dict[str, float]]`
**Functions**
- `_stable_seed_from_ctx(task_key: str, mode: str, goal: Optional[str], risk: Optional[str]) -> int`
- `_ensure_1d(vec: Any, d: Optional[int] = None) -> np.ndarray`
- `__new__(cls)`
- `_candidate_ids_from_request(self, req: SelectArmRequest) -> List[str]`
- `_build_candidate_set(self, all_arms_in_mode: List[PolicyArm], x_vec: np.ndarray, req: SelectArmRequest, mode: str) -> List[PolicyArm]`
- `_score_candidates(self, candidates: Iterable[PolicyArm], x_vec: np.ndarray) -> Dict[str, float]`
- `select_arm(self, request: SelectArmRequest, mode: str) -> Tuple[PolicyArm, Dict[str, float]]`
- `update(self, arm_id: str, reward: float) -> None`
- `get_last_scores_for_arm(self, arm_id: str) -> Optional[Dict[str, float]]`

### `D:\EcodiaOS\systems\synapse\core\reward.py`
**Classes**
- **RewardArbiter**  bases: ``
  - `__new__(cls)`
  - `__init__(self)`
  - `initialize(self) -> None`
  - `update_scalarization_weights(self, new_weights: Dict[str, float])`
  - `_norm01(v: Any) -> float`
  - `compute_reward_vector(self, metrics: Dict[str, Any]) -> List[float]`
  - `scalarize_reward(self, reward_vec: List[float]) -> float`
**Functions**
- `__new__(cls)`
- `__init__(self)`
- `initialize(self) -> None`
- `update_scalarization_weights(self, new_weights: Dict[str, float])`
- `_norm01(v: Any) -> float`
- `compute_reward_vector(self, metrics: Dict[str, Any]) -> List[float]`
- `scalarize_reward(self, reward_vec: List[float]) -> float`
- `log_outcome(self, episode_id: str, task_key: str, metrics: Dict[str, Any], simulator_prediction: Optional[Dict[str, Any]] = None, reward_vec_override: Optional[List[float]] = None) -> Tuple[float, List[float]]`

### `D:\EcodiaOS\systems\synapse\core\planner.py`
**Classes**
- **MetacognitivePlanner**  bases: ``
  - `__new__(cls)`
  - `determine_strategy(self, request: PolicyHintRequest) -> Dict[str, Any]`
**Functions**
- `_ctx_pick(primary: Optional[str], secondary: Optional[str], default: Optional[str]) -> Optional[str]`
- `__new__(cls)`
- `determine_strategy(self, request: PolicyHintRequest) -> Dict[str, Any]`

### `D:\EcodiaOS\systems\synapse\core\firewall.py`
**Classes**
- **NeuroSymbolicFirewall**  bases: ``
  - `__new__(cls)`
  - `validate_action(self, arm: PolicyArm, request: TaskContext) -> Tuple[bool, str]`
  - `get_safe_fallback_arm(self, mode: Optional[str] = None) -> PolicyArm`
**Functions**
- `__new__(cls)`
- `validate_action(self, arm: PolicyArm, request: TaskContext) -> Tuple[bool, str]`
- `get_safe_fallback_arm(self, mode: Optional[str] = None) -> PolicyArm`

### `D:\EcodiaOS\systems\synapse\core\genesis.py`
**Classes**
- **ToolGenesisModule**  bases: ``
  - `__new__(cls)`
  - `_request_llm_spec(self, task_key: str) -> Any`
  - `run_genesis_cycle(self)`
**Functions**
- `__new__(cls)`
- `_request_llm_spec(self, task_key: str) -> Any`
- `on_response(response: dict)`
- `run_genesis_cycle(self)`
- `start_genesis_loop()`

### `D:\EcodiaOS\systems\synapse\core\episode.py`
**Functions**
- `start_episode(mode: str, task_key: str, chosen_arm_id: Optional[str] = None, parent_episode_id: Optional[str] = None, context: Optional[Dict[str, Any]] = None, audit_trace: Optional[Dict[str, Any]] = None) -> str`
- `end_episode(episode_id: str, reward: float, metrics: Optional[Dict[str, Any]] = None) -> None`

### `D:\EcodiaOS\systems\synapse\core\arm_genesis.py`
**Functions**
- `_generate_base_graph(task: str) -> PolicyGraph`
- `_mutations(base_graph: PolicyGraph, count: int) -> List[PolicyGraph]`
- `_registry_reload() -> None`
- `_prune_underperformers()`
- `genesis_scan_and_mint() -> None`
- `_mint_graphs(graphs: List[PolicyGraph], mode: str, task: str) -> int`

### `D:\EcodiaOS\systems\synapse\core\register_arm.py`
**Functions**
- `register_arm(arm_id: str, mode: str, config: Dict[str, Any]) -> None`

### `D:\EcodiaOS\systems\synapse\core\meta_controller.py`
**Classes**
- **MetaController**  bases: ``
  - `__new__(cls)`
  - `initialize(self) -> None`
  - `select_strategy(self, request: TaskContext) -> Dict[str, Any]`
  - `allocate_budget(self, request: TaskContext) -> Dict[str, int]`
**Functions**
- `_load_json_env(name: str) -> Optional[Dict[str, Any]]`
- `_validate_strategy_map(m: Dict[str, Any]) -> Dict[str, Dict[str, Any]]`
- `_validate_budget_map(m: Dict[str, Any]) -> Dict[str, Dict[str, int]]`
- `__new__(cls)`
- `initialize(self) -> None`
- `select_strategy(self, request: TaskContext) -> Dict[str, Any]`
- `allocate_budget(self, request: TaskContext) -> Dict[str, int]`

### `D:\EcodiaOS\systems\synapse\core\snapshots.py`
**Functions**
- `get_component_version(component_name: str) -> str`
- `stamp() -> Dict[str, Any]`

### `D:\EcodiaOS\systems\synapse\core\governor.py`
**Classes**
- **Governor**  bases: ``
  - `__new__(cls)`
  - `_run_regression_suite(self, patch: str) -> Tuple[bool, Dict[str, Any]]`
  - `_run_historical_replay(self, patch: str) -> Tuple[bool, Dict[str, Any]]`
  - `_run_sentinel_checks(self, patch: str) -> Tuple[bool, Dict[str, Any]]`
  - `verify_and_apply_upgrade(self, proposal: PatchProposal) -> Dict[str, Any]`
**Functions**
- `_proposal_id(proposal: PatchProposal) -> str`
- `_record_verification(proposal_id: str, summary: str, steps: Dict[str, Dict[str, Any]], status: str) -> None`
- `__new__(cls)`
- `_run_regression_suite(self, patch: str) -> Tuple[bool, Dict[str, Any]]`
- `_run_historical_replay(self, patch: str) -> Tuple[bool, Dict[str, Any]]`
- `_run_sentinel_checks(self, patch: str) -> Tuple[bool, Dict[str, Any]]`
- `verify_and_apply_upgrade(self, proposal: PatchProposal) -> Dict[str, Any]`

### `D:\EcodiaOS\systems\synapse\core\registry_bootstrap.py`
**Functions**
- `_build_noop_pg_dict(arm_id: str) -> Dict[str, Any]`
- `_coerce_policy_graph(pg_like: Dict[str, Any])`
- `ensure_minimum_arms() -> None`

### `D:\EcodiaOS\systems\synapse\training\__init__.py`

### `D:\EcodiaOS\systems\synapse\training\offline_updater.py`

### `D:\EcodiaOS\systems\synapse\training\meta_controller.py`
**Classes**
- **MetaController**  bases: ``
  - `__new__(cls)`
  - `initialize(self)`
  - `run_tuning_cycle(self)`
**Functions**
- `__new__(cls)`
- `initialize(self)`
- `run_tuning_cycle(self)`
- `start_meta_controller_loop()`

### `D:\EcodiaOS\systems\synapse\training\adversary.py`
**Classes**
- **AdversarialAgent**  bases: ``
  - `__new__(cls)`
  - `_generate_challenging_task_context(self) -> TaskContext`
  - `_update_task_values(self, task_key: str, synapse_reward: float)`
  - `run_adversarial_cycle(self)`
**Functions**
- `__new__(cls)`
- `_generate_challenging_task_context(self) -> TaskContext`
- `_update_task_values(self, task_key: str, synapse_reward: float)`
- `run_adversarial_cycle(self)`
- `start_adversary_loop()`

### `D:\EcodiaOS\systems\synapse\training\bandit_state.py`
**Functions**
- `mark_dirty(arm_id: str) -> None`
- `_drain_dirty(batch_size: int) -> Set[str]`
- `_flush_batch(arm_ids: Set[str]) -> None`
- `flush_now(batch_size: int = 128) -> None`
- `_flusher_loop(interval_sec: float, batch_size: int) -> None`
- `start_background_flusher(interval_sec: float = 30.0, batch_size: int = 128) -> None`
- `stop_background_flusher() -> None`

### `D:\EcodiaOS\systems\synapse\training\neural_linear.py`
**Classes**
- **NeuralLinearBanditHead**  bases: ``
  - `__init__(self, arm_id: str, dimensions: int, lambda_prior: float = 1.0, initial_state: Optional[Dict[str, Any]] = None, gamma: float = 0.995)`
  - `get_state(self) -> Dict[str, Any]`
  - `_posterior_mean(self) -> np.ndarray`
  - `sample_theta(self) -> np.ndarray`
  - `get_theta_mean(self) -> np.ndarray`
  - `score(self, x: np.ndarray) -> float`
  - `update(self, x: np.ndarray, r: float, gamma: Optional[float] = None) -> None`
- **NeuralLinearArmManager**  bases: ``
  - `__new__(cls)`
  - `__init__(self)`
  - `dimensions(self) -> int`
  - `_hidx(self, token: str) -> int`
  - `encode(self, raw_context: Dict[str, Any]) -> np.ndarray`
**Functions**
- `_pack_matrix(M: np.ndarray) -> Tuple[list, Tuple[int, int]]`
- `_unpack_matrix(flat: list, shape: Tuple[int, int]) -> np.ndarray`
- `_ensure_col_vec(x: np.ndarray) -> np.ndarray`
- `_stable_cholesky(A: np.ndarray, max_tries: int = 5) -> np.ndarray`
- `__init__(self, arm_id: str, dimensions: int, lambda_prior: float = 1.0, initial_state: Optional[Dict[str, Any]] = None, gamma: float = 0.995)`
- `get_state(self) -> Dict[str, Any]`
- `_posterior_mean(self) -> np.ndarray`
- `sample_theta(self) -> np.ndarray`
- `get_theta_mean(self) -> np.ndarray`
- `score(self, x: np.ndarray) -> float`
- `update(self, x: np.ndarray, r: float, gamma: Optional[float] = None) -> None`
- `__new__(cls)`
- `__init__(self)`
- `dimensions(self) -> int`
- `_hidx(self, token: str) -> int`
- `encode(self, raw_context: Dict[str, Any]) -> np.ndarray`

### `D:\EcodiaOS\systems\synapse\training\encoder_trainer.py`
**Classes**
- **EncoderTrainer**  bases: ``
  - `fetch_training_data(self, limit: int = 10000) -> List[Dict[str, Any]]`
  - `train(self, episodes: List[Dict[str, Any]])`
- **EncoderModel**  bases: ``
  - `__init__(self, input_dim, hidden_dim, output_dim)`
  - `forward(self, x)`
  - `train(self)`
**Functions**
- `fetch_training_data(self, limit: int = 10000) -> List[Dict[str, Any]]`
- `train(self, episodes: List[Dict[str, Any]])`
- `__init__(self, input_dim, hidden_dim, output_dim)`
- `forward(self, x)`
- `train(self)`
- `run_training_job()`

### `D:\EcodiaOS\systems\synapse\training\run_offline_updates.py`
**Functions**
- `run_full_offline_pipeline()`

### `D:\EcodiaOS\systems\synapse\training\self_model_trainer.py`
**Classes**
- **SelfModelTrainer**  bases: ``
  - `__new__(cls)`
  - `_fetch_training_data(self, limit: int = 5000) -> List[Dict[str, Any]]`
  - `train_cycle(self)`
**Functions**
- `_risk_score(val: Any) -> float`
- `_budget_score(val: Any) -> float`
- `_safe_len(v: Any) -> int`
- `_vectorize_context(ctx: Dict[str, Any]) -> List[float]`
- `_build_dataset(rows: List[Dict[str, Any]]) -> Tuple[np.ndarray, np.ndarray]`
- `_pad(v: List[float], d: int) -> List[float]`
- `_standardize(X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]`
- `_ridge_fit(X: np.ndarray, Y: np.ndarray, l2: float = 0.01) -> Tuple[np.ndarray, np.ndarray]`
- `_metrics(Y_true: np.ndarray, Y_pred: np.ndarray) -> Dict[str, float]`
- `_persist_model(W: np.ndarray, b: np.ndarray, mean: np.ndarray, std: np.ndarray, dims_in: int, dims_out: int, metrics: Dict[str, float]) -> None`
- `__new__(cls)`
- `_fetch_training_data(self, limit: int = 5000) -> List[Dict[str, Any]]`
- `train_cycle(self)`

### `D:\EcodiaOS\systems\synapse\training\tom_trainer.py`
**Classes**
- **TheoryOfMindTrainer**  bases: ``
  - `__new__(cls)`
  - `_fetch_training_data(self, limit: int = 200) -> List[Dict[str, Any]]`
  - `_create_training_samples(self, transcripts: List[Dict[str, Any]]) -> Dict[str, List[str]]`
  - `train_cycle(self)`
**Functions**
- `_tok(s: str) -> List[str]`
- `_build_sequences(samples: List[str]) -> List[List[str]]`
- `_build_vocab(seqs: List[List[str]], max_vocab: int) -> Tuple[Dict[str, int], List[str]]`
- `_id_or_unk(stoi: Dict[str, int], w: str) -> int`
- `_unigram_bigram_counts(seqs: List[List[str]], stoi: Dict[str, int]) -> Tuple[np.ndarray, np.ndarray]`
- `_perplexity(seqs: List[List[str]], uni: np.ndarray, bi: np.ndarray, alpha: float) -> float`
- `_evaluate_role(seqs: List[List[str]], stoi: Dict[str, int], uni: np.ndarray, bi: np.ndarray, alpha: float) -> float`
- `_topk_table(stoi: Dict[str, int], itos: List[str], uni: np.ndarray, bi: np.ndarray, alpha: float) -> List[Dict[str, Any]]`
- `_persist_role_model(role: str, vocab: List[str], unigram_counts: List[float], topk_table_payload: List[Dict[str, Any]], alpha: float, metrics: Dict[str, float]) -> None`
- `__new__(cls)`
- `_fetch_training_data(self, limit: int = 200) -> List[Dict[str, Any]]`
- `_create_training_samples(self, transcripts: List[Dict[str, Any]]) -> Dict[str, List[str]]`
- `train_cycle(self)`

### `D:\EcodiaOS\systems\synapse\training\attention_trainer.py`
**Classes**
- **AttentionRankerTrainer**  bases: ``
  - `__new__(cls)`
  - `_fetch_training_data(self, limit: int = 1000) -> List[Dict[str, Any]]`
  - `_create_training_samples(self, deliberations: List[Dict[str, Any]])`
  - `train_cycle(self)`
**Functions**
- `_sigmoid(z: np.ndarray) -> np.ndarray`
- `_vectorize_cognit(c: Dict[str, Any]) -> List[float]`
- `_build_samples(delibs: List[Dict[str, Any]]) -> Tuple[np.ndarray, np.ndarray]`
- `_train_logreg(X: np.ndarray, y: np.ndarray, l2: float = 0.01, lr: float = 0.05, epochs: int = 200, batch_size: int = 128, seed: int = 13) -> Tuple[np.ndarray, float, Dict[str, float]]`
- `batch_iter()`
- `_persist_model(weights: List[float], bias: float, metrics: Dict[str, float]) -> None`
- `__new__(cls)`
- `_fetch_training_data(self, limit: int = 1000) -> List[Dict[str, Any]]`
- `_create_training_samples(self, deliberations: List[Dict[str, Any]])`
- `train_cycle(self)`

### `D:\EcodiaOS\systems\synapse\sdk\affordances.py`
**Functions**
- `validate_affordance(a: Dict[str, Any]) -> None`
- `normalize_affordances(items: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]`

### `D:\EcodiaOS\systems\synapse\sdk\client.py`
**Classes**
- **SynapseClient**  bases: ``
  - `_post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]`
  - `_get(self, path: str) -> Dict[str, Any]`
  - `select_arm(self, task_ctx: TaskContext, candidates: Optional[List[Candidate]] = None) -> SelectArmResponse`
  - `select_arm_simple(self, task_key: str, goal: Optional[str] = None, risk_level: Optional[str] = None, budget: Optional[str] = None, candidate_ids: Optional[List[str]] = None) -> SelectArmResponse`
  - `continue_option(self, episode_id: str, last_step_outcome: Dict[str, Any]) -> ContinueResponse`
  - `repair_skill_step(self, episode_id: str, failed_step_index: int, error_observation: Dict[str, Any]) -> RepairResponse`
  - `get_budget(self, task_key: str) -> BudgetResponse`
  - `log_outcome(self, episode_id: str, task_key: str, metrics: Dict[str, Any], simulator_prediction: Optional[Dict[str, Any]] = None) -> LogOutcomeResponse`
  - `ingest_preference(self, winner: str, loser: str, source: Optional[str] = None) -> Dict[str, Any]`
  - `submit_upgrade_proposal(self, proposal: PatchProposal) -> Dict[str, Any]`
  - `reload_registry(self) -> Dict[str, Any]`
  - `list_tools(self) -> Dict[str, Any]`
  - `get_values_comparison_pair(self) -> ComparisonPairResponse`
  - `submit_values_preference(self, req: SubmitPreferenceRequest) -> Dict[str, Any]`
**Functions**
- `_post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]`
- `_get(self, path: str) -> Dict[str, Any]`
- `select_arm(self, task_ctx: TaskContext, candidates: Optional[List[Candidate]] = None) -> SelectArmResponse`
- `select_arm_simple(self, task_key: str, goal: Optional[str] = None, risk_level: Optional[str] = None, budget: Optional[str] = None, candidate_ids: Optional[List[str]] = None) -> SelectArmResponse`
- `continue_option(self, episode_id: str, last_step_outcome: Dict[str, Any]) -> ContinueResponse`
- `repair_skill_step(self, episode_id: str, failed_step_index: int, error_observation: Dict[str, Any]) -> RepairResponse`
- `get_budget(self, task_key: str) -> BudgetResponse`
- `log_outcome(self, episode_id: str, task_key: str, metrics: Dict[str, Any], simulator_prediction: Optional[Dict[str, Any]] = None) -> LogOutcomeResponse`
- `ingest_preference(self, winner: str, loser: str, source: Optional[str] = None) -> Dict[str, Any]`
- `submit_upgrade_proposal(self, proposal: PatchProposal) -> Dict[str, Any]`
- `reload_registry(self) -> Dict[str, Any]`
- `list_tools(self) -> Dict[str, Any]`
- `get_values_comparison_pair(self) -> ComparisonPairResponse`
- `submit_values_preference(self, req: SubmitPreferenceRequest) -> Dict[str, Any]`

### `D:\EcodiaOS\systems\synapse\sdk\context.py`
**Functions**
- `build_context(tenant: Optional[str] = None, actor: Optional[str] = None, resource_descriptors: Optional[List[Dict[str, Any]]] = None, risk: Optional[str] = None, budget: Optional[str] = None, pii_tags: Optional[List[str]] = None, data_domains: Optional[List[str]] = None, latency_budget_ms: Optional[int] = None, sla_deadline: Optional[str] = None, graph_refs: Optional[Dict[str, Any]] = None, observability: Optional[Dict[str, Any]] = None, context_vector: Optional[List[float]] = None, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]`

### `D:\EcodiaOS\systems\synapse\sdk\decorators.py`
**Functions**
- `evolutionary(task_key_fn: TaskKeyFn, mode_hint: Optional[str] = None, metrics_fn: Optional[MetricsFn] = None, affordances_fn: Optional[AffordancesFn] = None)`
- `deco(fn)`
- `wrapped(context: Dict[str, Any], *args, **kwargs)`

### `D:\EcodiaOS\systems\synapse\sdk\hint_ext.py`
**Functions**
- `_to_dict(model: Any) -> Dict[str, Any]`
- `handle_policy_hint(req: PolicyHintRequest) -> PolicyHintResponse`
- `_surrogate_loss(graph, x) -> float`

### `D:\EcodiaOS\systems\synapse\policy\policy_dsl.py`
**Classes**
- **PolicyNode** _(pydantic)_  bases: `BaseModel`
- **PolicyEdge** _(pydantic)_  bases: `BaseModel`
- **PolicyConstraint** _(pydantic)_  bases: `BaseModel`
- **PolicyGraph** _(pydantic)_  bases: `BaseModel`
  - `canonical_hash(self) -> str`
**Functions**
- `canonical_hash(self) -> str`

### `D:\EcodiaOS\systems\synapse\critic\offpolicy.py`
**Classes**
- **Critic**  bases: ``
  - `__new__(cls)`
  - `_load_model(self)`
  - `fetch_training_data(self, limit: int = 5000) -> List[Dict[str, Any]]`
  - `fit_nightly(self)`
  - `score(self, task_ctx: TaskContext, arm_id: str) -> float`
  - `rerank_topk(self, request: TaskContext, candidate_scores: Dict[str, float], blend_factor: float = 0.3) -> str`
**Functions**
- `_featurize_episode(log: Dict[str, Any]) -> Optional[Dict[str, Any]]`
- `__new__(cls)`
- `_load_model(self)`
- `fetch_training_data(self, limit: int = 5000) -> List[Dict[str, Any]]`
- `fit_nightly(self)`
- `score(self, task_ctx: TaskContext, arm_id: str) -> float`
- `rerank_topk(self, request: TaskContext, candidate_scores: Dict[str, float], blend_factor: float = 0.3) -> str`

### `D:\EcodiaOS\systems\synapse\firewall\smt_guard.py`
**Functions**
- `check_smt_constraints(policy: PolicyGraph) -> Tuple[bool, str]`

### `D:\EcodiaOS\systems\synapse\world\simulator.py`
**Classes**
- **SimulationPrediction** _(pydantic)_  bases: `BaseModel`
- **WorldModel**  bases: ``
  - `__new__(cls)`
  - `load_model(self) -> None`
  - `_featurize(self, task_ctx: TaskContext) -> Dict[str, float]`
  - `_safe_sigma_from_models(models: List[Any], X: Any) -> float`
  - `simulate(self, plan_graph: PolicyGraph, task_ctx: TaskContext) -> SimulationPrediction`
**Functions**
- `__new__(cls)`
- `load_model(self) -> None`
- `_featurize(self, task_ctx: TaskContext) -> Dict[str, float]`
- `_safe_sigma_from_models(models: List[Any], X: Any) -> float`
- `simulate(self, plan_graph: PolicyGraph, task_ctx: TaskContext) -> SimulationPrediction`

### `D:\EcodiaOS\systems\synapse\world\diff_sim.py`
**Functions**
- `_deepcopy_graph(g: PolicyGraph) -> PolicyGraph`
- `_evaluate(loss_fn: Callable[[PolicyGraph, np.ndarray], float], graph: PolicyGraph, x: np.ndarray) -> float`
- `_numeric_params(graph: PolicyGraph) -> List[Tuple[int, str, float]]`
- `_guess_bounds(node: Any, key: str, v: float) -> Optional[Tuple[float, float]]`
- `_clamp(val: float, bounds: Optional[Tuple[float, float]]) -> float`
- `_finite_diff_grad(loss_fn: Callable[[PolicyGraph, np.ndarray], float], base_graph: PolicyGraph, x: np.ndarray, idx: int, key: str, eps: float) -> float`
- `grad_optimize(plan_graph: PolicyGraph, x: np.ndarray, loss_fn: Callable, steps: int = 8) -> PolicyGraph`
- `_apply_update(src_graph: PolicyGraph, factor: float) -> PolicyGraph`

### `D:\EcodiaOS\systems\synapse\world\world_model_trainer.py`
**Classes**
- **WorldModelTrainer**  bases: ``
  - `__init__(self) -> None`
  - `_featurize_episode(self, episode: Dict[str, Any]) -> Optional[Dict[str, float]]`
  - `fetch_training_data(self, limit: int = 20000) -> List[Dict[str, Any]]`
  - `_build_dataset(self, episodes: List[Dict[str, Any]]) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[DictVectorizer]]`
  - `_train_models(self, X_tr: np.ndarray, Y_tr: np.ndarray, random_state: int = 42) -> List[GradientBoostingRegressor]`
  - `_evaluate(self, X_val: np.ndarray, Y_val: np.ndarray, models: List[GradientBoostingRegressor]) -> Dict[str, float]`
  - `_atomic_save(self, payload: Dict[str, Any], path: Path) -> None`
  - `_persist_model_card(self, dims_in: int, dims_out: int, metrics: Dict[str, float]) -> None`
  - `train_and_save_model(self) -> None`
**Functions**
- `__init__(self) -> None`
- `_featurize_episode(self, episode: Dict[str, Any]) -> Optional[Dict[str, float]]`
- `fetch_training_data(self, limit: int = 20000) -> List[Dict[str, Any]]`
- `_build_dataset(self, episodes: List[Dict[str, Any]]) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[DictVectorizer]]`
- `_train_models(self, X_tr: np.ndarray, Y_tr: np.ndarray, random_state: int = 42) -> List[GradientBoostingRegressor]`
- `_evaluate(self, X_val: np.ndarray, Y_val: np.ndarray, models: List[GradientBoostingRegressor]) -> Dict[str, float]`
- `_atomic_save(self, payload: Dict[str, Any], path: Path) -> None`
- `_persist_model_card(self, dims_in: int, dims_out: int, metrics: Dict[str, float]) -> None`
- `train_and_save_model(self) -> None`

### `D:\EcodiaOS\systems\synapse\explain\minset.py`
**Functions**
- `min_explanation(x: np.ndarray, theta_chosen: np.ndarray, theta_alt: np.ndarray, feature_names: Optional[List[str]] = None) -> Dict[str, Any]`

### `D:\EcodiaOS\systems\synapse\explain\probes.py`
**Classes**
- **MetaProbe**  bases: ``
  - `__new__(cls)`
  - `predict_risk(self, trace: Dict[str, Any]) -> Dict[str, float]`
**Functions**
- `_clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float`
- `_safe_float(v: Any, default: float = 0.0) -> float`
- `_topk_stats(scores: Dict[str, float], k: int = 3) -> Tuple[List[float], float, float]`
- `_extract_sequence(trace: Dict[str, Any]) -> List[str]`
- `_sim_uncertainty(trace: Dict[str, Any]) -> float`
- `_calc_spec_drift(trace: Dict[str, Any]) -> float`
- `_calc_overfit(trace: Dict[str, Any]) -> float`
- `_calc_fragility(trace: Dict[str, Any]) -> float`
- `_calc_loop(trace: Dict[str, Any]) -> float`
- `__new__(cls)`
- `predict_risk(self, trace: Dict[str, Any]) -> Dict[str, float]`

### `D:\EcodiaOS\systems\synapse\qd\map_elites.py`
**Classes**
- **QDArchive**  bases: ``
  - `__new__(cls)`
  - `__init__(self)`
  - `get_descriptor(self, arm_id: str, metrics: Dict[str, Any]) -> Niche`
  - `insert(self, arm_id: str, score: float, metrics: Dict[str, Any])`
  - `sample_niche(self) -> Optional[Niche]`
  - `get_champion_from_niche(self, niche: Niche) -> Optional[str]`
**Functions**
- `_norm_str(x: Any, default: str = 'unknown') -> str`
- `_risk_tier(metrics: Dict[str, Any]) -> str`
- `_cost_tier(metrics: Dict[str, Any]) -> str`
- `_task_family(metrics: Dict[str, Any]) -> str`
- `__new__(cls)`
- `__init__(self)`
- `get_descriptor(self, arm_id: str, metrics: Dict[str, Any]) -> Niche`
- `insert(self, arm_id: str, score: float, metrics: Dict[str, Any])`
- `sample_niche(self) -> Optional[Niche]`
- `get_champion_from_niche(self, niche: Niche) -> Optional[str]`

### `D:\EcodiaOS\systems\synapse\qd\replicator.py`
**Classes**
- **Replicator**  bases: ``
  - `__new__(cls)`
  - `__init__(self, learning_rate: float = 0.1)`
  - `update_fitness(self, niche: Niche, fitness_score: float)`
  - `_normalize_shares(self)`
  - `rebalance_shares(self)`
  - `sample_niche(self) -> Optional[Niche]`
  - `get_genesis_allocation(self, total_budget: int) -> Dict[Niche, int]`
**Functions**
- `__new__(cls)`
- `__init__(self, learning_rate: float = 0.1)`
- `update_fitness(self, niche: Niche, fitness_score: float)`
- `_normalize_shares(self)`
- `rebalance_shares(self)`
- `sample_niche(self) -> Optional[Niche]`
- `get_genesis_allocation(self, total_budget: int) -> Dict[Niche, int]`

### `D:\EcodiaOS\systems\synapse\economics\roi.py`
**Classes**
- **ROIManager**  bases: ``
  - `__new__(cls)`
  - `__init__(self)`
  - `update_roi(self, arm_id: str, scalar_reward: float, metrics: Dict[str, Any])`
  - `get_underperforming_arms(self, percentile_threshold: int = 10) -> list[str]`
**Functions**
- `__new__(cls)`
- `__init__(self)`
- `update_roi(self, arm_id: str, scalar_reward: float, metrics: Dict[str, Any])`
- `get_underperforming_arms(self, percentile_threshold: int = 10) -> list[str]`

### `D:\EcodiaOS\systems\synapse\rerank\episodic_knn.py`
**Classes**
- **EpisodicKNN**  bases: ``
  - `__new__(cls)`
  - `__init__(self, capacity: int = 5000)`
  - `update(self, x: np.ndarray, best_arm: str, reward: float)`
  - `suggest(self, x: np.ndarray, k: int = 5) -> List[str]`
**Functions**
- `__new__(cls)`
- `__init__(self, capacity: int = 5000)`
- `update(self, x: np.ndarray, best_arm: str, reward: float)`
- `suggest(self, x: np.ndarray, k: int = 5) -> List[str]`

### `D:\EcodiaOS\systems\synapse\meta\optimizer.py`
**Classes**
- **_EpisodeRow** _(dataclass)_  bases: ``
- **MetaOptimizer**  bases: ``
  - `__new__(cls)`
  - `_fetch_replay_data(self, limit: int = 5000) -> List[_EpisodeRow]`
  - `_fit_model(self, rows: List[_EpisodeRow]) -> Optional[Pipeline]`
  - `_predict_reward(self, model: Pipeline, cmode: str, cb: float, rd: int) -> float`
  - `_search_best(self, model: Pipeline) -> Dict[str, Any]`
  - `run_optimization_cycle(self) -> Dict[str, Any]`
**Functions**
- `__new__(cls)`
- `_fetch_replay_data(self, limit: int = 5000) -> List[_EpisodeRow]`
- `_fit_model(self, rows: List[_EpisodeRow]) -> Optional[Pipeline]`
- `_predict_reward(self, model: Pipeline, cmode: str, cb: float, rd: int) -> float`
- `_search_best(self, model: Pipeline) -> Dict[str, Any]`
- `run_optimization_cycle(self) -> Dict[str, Any]`

### `D:\EcodiaOS\systems\synapse\safety\sentinels.py`
**Classes**
- **GoodhartSentinel**  bases: ``
  - `__new__(cls)`
  - `_featurize_trace(self, trace: Dict[str, Any]) -> Optional[np.ndarray]`
  - `fit(self)`
  - `check(self, trace: Dict[str, Any]) -> Optional[Dict[str, Any]]`
- **SentinelManager**  bases: ``
  - `__new__(cls)`
  - `_freeze_genesis(self, reason: str)`
  - `_throttle_budgets(self, task_key: str, reason: str)`
  - `analyze_patch_for_risks(self, patch_diff: str) -> Optional[Dict[str, Any]]`
  - `run_sentinel_check(self, recent_traces: List[Dict[str, Any]])`
**Functions**
- `__new__(cls)`
- `_featurize_trace(self, trace: Dict[str, Any]) -> Optional[np.ndarray]`
- `fit(self)`
- `check(self, trace: Dict[str, Any]) -> Optional[Dict[str, Any]]`
- `__new__(cls)`
- `_freeze_genesis(self, reason: str)`
- `_throttle_budgets(self, task_key: str, reason: str)`
- `analyze_patch_for_risks(self, patch_diff: str) -> Optional[Dict[str, Any]]`
- `run_sentinel_check(self, recent_traces: List[Dict[str, Any]])`

### `D:\EcodiaOS\systems\synapse\experiments\active.py`
**Classes**
- **ExperimentDesigner**  bases: ``
  - `__new__(cls)`
  - `design_probe(self, uncertainty_map: Dict[str, float]) -> Optional[TaskContext]`
**Functions**
- `_risk_from_tokens(tokens: list[str], default: str = 'medium') -> str`
- `_budget_from_tokens(tokens: list[str], default: str = 'constrained') -> str`
- `_parse_niche_key(key: str) -> Optional[Dict[str, Any]]`
- `_parse_sim_uncertainty_key(key: str) -> Optional[str]`
- `__new__(cls)`
- `design_probe(self, uncertainty_map: Dict[str, float]) -> Optional[TaskContext]`

### `D:\EcodiaOS\systems\synapse\values\learner.py`
**Classes**
- **ValueLearner**  bases: ``
  - `__new__(cls)`
  - `_fetch_preferences(self, limit: int = 500) -> List[Dict[str, Any]]`
  - `_bradley_terry_update(self, weights: np.ndarray, preferences: List[Dict[str, Any]], learning_rate = 0.01, epochs = 10) -> np.ndarray`
  - `run_learning_cycle(self)`
**Functions**
- `__new__(cls)`
- `_fetch_preferences(self, limit: int = 500) -> List[Dict[str, Any]]`
- `_bradley_terry_update(self, weights: np.ndarray, preferences: List[Dict[str, Any]], learning_rate = 0.01, epochs = 10) -> np.ndarray`
- `run_learning_cycle(self)`

### `D:\EcodiaOS\systems\synapse\robust\ood.py`
**Classes**
- **OODDetector**  bases: ``
  - `__new__(cls)`
  - `__init__(self)`
  - `initialize_distribution(self)`
  - `update_and_persist_distribution(self, new_vectors: np.ndarray)`
  - `check_shift(self, x: np.ndarray) -> Dict[str, Any]`
**Functions**
- `__new__(cls)`
- `__init__(self)`
- `initialize_distribution(self)`
- `update_and_persist_distribution(self, new_vectors: np.ndarray)`
- `check_shift(self, x: np.ndarray) -> Dict[str, Any]`

### `D:\EcodiaOS\systems\synapse\obs\schemas.py`
**Classes**
- **GlobalStats** _(pydantic)_  bases: `BaseModel`
- **NicheData** _(pydantic)_  bases: `BaseModel`
- **QDCoverage** _(pydantic)_  bases: `BaseModel`
- **ROITrend** _(pydantic)_  bases: `BaseModel`
- **ROITrends** _(pydantic)_  bases: `BaseModel`
- **EpisodeTrace** _(pydantic)_  bases: `BaseModel`

### `D:\EcodiaOS\systems\synapse\obs\queries.py`
**Functions**
- `get_global_stats() -> Dict[str, Any]`
- `get_qd_coverage_data() -> Dict[str, Any]`
- `get_full_episode_trace(episode_id: str) -> Optional[Dict[str, Any]]`

### `D:\EcodiaOS\systems\synapse\skills\schemas.py`
**Classes**
- **Option** _(pydantic)_  bases: `BaseModel`

### `D:\EcodiaOS\systems\synapse\skills\options.py`
**Classes**
- **OptionMiner**  bases: ``
  - `__new__(cls)`
  - `_fetch_successful_chains(self, min_length: int = 3, limit: int = 100) -> List[Dict]`
  - `mine_and_save_options(self)`
**Functions**
- `__new__(cls)`
- `_fetch_successful_chains(self, min_length: int = 3, limit: int = 100) -> List[Dict]`
- `mine_and_save_options(self)`

### `D:\EcodiaOS\systems\synapse\skills\manager.py`
**Classes**
- **SkillsManager**  bases: ``
  - `__new__(cls)`
  - `initialize(self)`
  - `select_best_option(self, context_vec: np.ndarray, task_ctx: TaskContext) -> Optional[Option]`
**Functions**
- `__new__(cls)`
- `initialize(self)`
- `select_best_option(self, context_vec: np.ndarray, task_ctx: TaskContext) -> Optional[Option]`

### `D:\EcodiaOS\systems\synapse\skills\executor.py`
**Classes**
- **ExecutionState** _(dataclass)_  bases: ``
- **OptionExecutor**  bases: ``
  - `start_execution(self, episode_id: str, option: Option) -> Optional[PolicyArm]`
  - `continue_execution(self, episode_id: str, last_step_outcome: Any) -> Optional[PolicyArm]`
  - `end_execution(self, episode_id: str)`
**Functions**
- `start_execution(self, episode_id: str, option: Option) -> Optional[PolicyArm]`
- `continue_execution(self, episode_id: str, last_step_outcome: Any) -> Optional[PolicyArm]`
- `end_execution(self, episode_id: str)`

### `D:\EcodiaOS\systems\simula\config.py`
**Classes**
- **SandboxSettings**  bases: `BaseSettings`
- **TimeoutSettings**  bases: `BaseSettings`
- **SimulaSettings**  bases: `BaseSettings`
  - `_parse_allowed_roots(cls, v)`
  - `_parse_unsandbox_flag(cls, v)`
  - `_harmonize_paths(self)`
**Functions**
- `_normalize_path_string(p: str) -> str`
- `_default_workspace_root() -> str`
- `_default_artifacts_root(ws_root: str) -> str`
- `_parse_allowed_roots(cls, v)`
- `_parse_unsandbox_flag(cls, v)`
- `_harmonize_paths(self)`

### `D:\EcodiaOS\systems\simula\agent\orchestrator.py`
**Classes**
- **AgentOrchestrator**  bases: ``
  - `__init__(self) -> None`
  - `_handle_skill_continuation(self, is_complete: bool, next_action: Optional[Dict]) -> Dict[str, Any]`
  - `_create_plan(self, steps: List[str]) -> Dict[str, Any]`
  - `_update_plan(self, step_index: int, new_status: str, notes: str = '') -> Dict[str, Any]`
  - `_execute_code_evolution(self, goal: str, step_details: Dict[str, Any], job_id: str) -> bool`
  - `_submit_for_review(self, summary: str, instruction: str = '') -> Dict[str, Any]`
  - `_submit_for_governance(self, summary: str) -> Dict[str, Any]`
  - `_think_next_action(self, goal: str) -> Dict[str, Any]`
  - `run(self, goal: str, objective_dict: Dict[str, Any]) -> Dict[str, Any]`
**Functions**
- `__init__(self) -> None`
- `_handle_skill_continuation(self, is_complete: bool, next_action: Optional[Dict]) -> Dict[str, Any]`
- `_create_plan(self, steps: List[str]) -> Dict[str, Any]`
- `_update_plan(self, step_index: int, new_status: str, notes: str = '') -> Dict[str, Any]`
- `_execute_code_evolution(self, goal: str, step_details: Dict[str, Any], job_id: str) -> bool`
- `_submit_for_review(self, summary: str, instruction: str = '') -> Dict[str, Any]`
- `_submit_for_governance(self, summary: str) -> Dict[str, Any]`
- `_think_next_action(self, goal: str) -> Dict[str, Any]`
- `_on_llm_response(response: dict)`
- `run(self, goal: str, objective_dict: Dict[str, Any]) -> Dict[str, Any]`

### `D:\EcodiaOS\systems\simula\agent\tools.py`
**Functions**
- `execute_system_tool(query: str, args: Dict[str, Any]) -> Dict[str, Any]`
- `finish(**kwargs)`
- `create_plan(**kwargs)`
- `update_plan(**kwargs)`
- `submit_code_for_multi_agent_review(**kwargs)`

### `D:\EcodiaOS\systems\simula\agent\tool_specs.py`

### `D:\EcodiaOS\systems\simula\client\synapse_client.py`
**Classes**
- **SynapseClient**  bases: ``
  - `_post(self, path: str, payload: Dict[str, Any], timeout: Optional[float] = None) -> Dict[str, Any]`
  - `_get(self, path: str, timeout: Optional[float] = None) -> Dict[str, Any]`
  - `select_arm(self, task_ctx: TaskContext, candidates: Optional[List[Candidate]] = None) -> SelectArmResponse`
  - `select_arm_simple(self, task_key: str, goal: Optional[str] = None, risk_level: Optional[str] = None, budget: Optional[str] = None, candidate_ids: Optional[List[str]] = None) -> SelectArmResponse`
  - `continue_option(self, episode_id: str, last_step_outcome: Dict[str, Any]) -> ContinueResponse`
  - `repair_skill(self, episode_id: str, failed_step_index: int, error_observation: Dict[str, Any]) -> RepairResponse`
  - `get_budget(self, task_key: str) -> BudgetResponse`
  - `log_outcome(self, episode_id: str, task_key: str, metrics: Dict[str, Any], simulator_prediction: Optional[Dict[str, Any]] = None) -> LogOutcomeResponse`
  - `submit_for_governance(self, proposal: Dict[str, Any]) -> Dict[str, Any]`
**Functions**
- `_post(self, path: str, payload: Dict[str, Any], timeout: Optional[float] = None) -> Dict[str, Any]`
- `_get(self, path: str, timeout: Optional[float] = None) -> Dict[str, Any]`
- `select_arm(self, task_ctx: TaskContext, candidates: Optional[List[Candidate]] = None) -> SelectArmResponse`
- `select_arm_simple(self, task_key: str, goal: Optional[str] = None, risk_level: Optional[str] = None, budget: Optional[str] = None, candidate_ids: Optional[List[str]] = None) -> SelectArmResponse`
- `continue_option(self, episode_id: str, last_step_outcome: Dict[str, Any]) -> ContinueResponse`
- `repair_skill(self, episode_id: str, failed_step_index: int, error_observation: Dict[str, Any]) -> RepairResponse`
- `get_budget(self, task_key: str) -> BudgetResponse`
- `log_outcome(self, episode_id: str, task_key: str, metrics: Dict[str, Any], simulator_prediction: Optional[Dict[str, Any]] = None) -> LogOutcomeResponse`
- `submit_for_governance(self, proposal: Dict[str, Any]) -> Dict[str, Any]`

### `D:\EcodiaOS\systems\simula\code_sim\eval_types.py`
**Classes**
- **MockTelemetry**  bases: ``
  - `reward(self, *args, **kwargs)`
- **EvalResult** _(dataclass)_  bases: ``
  - `as_dict(self) -> Dict`
  - `hard_gates_ok(self) -> bool`
- **RewardAggregator**  bases: ``
  - `__init__(self, cfg: Optional[Dict[str, Any]] = None)`
  - `_calibrate(self, name: str, value: float) -> float`
  - `score(self, eval_result: EvalResult) -> float`
  - `explain(self, eval_result: EvalResult) -> Dict[str, float]`
**Functions**
- `reward(self, *args, **kwargs)`
- `as_dict(self) -> Dict`
- `hard_gates_ok(self) -> bool`
- `__init__(self, cfg: Optional[Dict[str, Any]] = None)`
- `_calibrate(self, name: str, value: float) -> float`
- `score(self, eval_result: EvalResult) -> float`
- `explain(self, eval_result: EvalResult) -> Dict[str, float]`

### `D:\EcodiaOS\systems\simula\code_sim\loop.py`
**Classes**
- **JsonLogFormatter**  bases: `logging.Formatter`
  - `format(self, record: logging.LogRecord) -> str`
- **SandboxCfg** _(dataclass)_  bases: ``
- **OrchestratorCfg** _(dataclass)_  bases: ``
- **SimulaConfig** _(dataclass)_  bases: ``
  - `load(path: Optional[Path] = None) -> 'SimulaConfig'`
- **ArtifactStore**  bases: ``
  - `__init__(self, root_dir: Path, run_id: str)`
  - `write_text(self, rel: str, content: str) -> Path`
  - `save_candidate(self, step_name: str, iter_idx: int, file_rel: str, patch: str, tag: str = '') -> Path`
**Functions**
- `format(self, record: logging.LogRecord) -> str`
- `setup_logging(verbose: bool, run_dir: Path) -> None`
- `sha1(s: str) -> str`
- `load(path: Optional[Path] = None) -> 'SimulaConfig'`
- `__init__(self, root_dir: Path, run_id: str)`
- `write_text(self, rel: str, content: str) -> Path`
- `save_candidate(self, step_name: str, iter_idx: int, file_rel: str, patch: str, tag: str = '') -> Path`

### `D:\EcodiaOS\systems\simula\code_sim\planner.py`
**Functions**
- `_as_list(x: Any) -> List[Any]`
- `_require_keys(d: Dict[str, Any], keys: List[str], ctx: str) -> None`
- `_get(obj: Any, key: str, default = None)`
- `_get_path(obj: Any, path: Sequence[str], default = None)`
- `_normalize_targets(raw_targets: Any) -> List[StepTarget]`
- `_normalize_tests(step_dict: Dict[str, Any], objective_obj: Objective) -> List[str]`
- `_validate_iterations(obj_dict: Dict[str, Any]) -> Tuple[int, float]`
- `_validate_acceptance(obj_dict: Dict[str, Any]) -> None`
- `_normalize_steps_list(obj_dict: Dict[str, Any]) -> List[Dict[str, Any]]`
- `_build_step(step_dict: Dict[str, Any], objective_dict: Dict[str, Any], objective_obj: Objective) -> Step`
- `plan_from_objective(objective_dict: Dict[str, Any]) -> Plan`
- `match_tests_in_repo(tests: List[str], repo_root: Path) -> List[Path]`
- `pretty_plan(plan: Plan) -> str`

### `D:\EcodiaOS\systems\simula\code_sim\portfolio.py`
**Functions**
- `_generate_single_candidate(step: Any, strategy: str) -> Optional[str]`
- `generate_candidate_portfolio(job_meta: Dict, step: Any) -> List[Dict[str, Any]]`

### `D:\EcodiaOS\systems\simula\code_sim\prompts.py`
**Functions**
- `_read_file_snippet(path: Path, max_lines: int = 60) -> str`
- `_ensure_identity(spec: str, identity: Optional[Dict[str, Any]]) -> Dict[str, Any]`
- `build_plan_prompt(spec: str, targets: List[Dict[str, Any]], identity: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]`
- `build_file_prompt(spec: str, identity: Optional[Dict[str, Any]] = None, file_plan: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]`

### `D:\EcodiaOS\systems\simula\code_sim\telemetry.py`
**Classes**
- **Telemetry** _(dataclass)_  bases: ``
  - `from_env(cls) -> 'Telemetry'`
  - `enable_if_env(self) -> None`
  - `_ensure_dirs(self) -> None`
  - `_job_file(self, job_id: str) -> str`
  - `_write(self, job_id: str, event: Dict[str, Any]) -> None`
  - `start_job(self, job_id: Optional[str] = None, job_meta: Optional[Dict[str, Any]] = None) -> str`
  - `end_job(self, status: str = 'ok', extra: Optional[Dict[str, Any]] = None) -> None`
  - `llm_call(self, model: str, tokens_in: int, tokens_out: int, meta: Optional[Dict[str, Any]] = None) -> None`
  - `reward(self, value: float, reason: str = '', meta: Optional[Dict[str, Any]] = None) -> None`
  - `log_event(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> None`
  - `tool_event(self, phase: str, name: str, args: Any = None, result: Any = None, ok: Optional[bool] = None, err: Optional[str] = None, extra: Optional[Dict[str, Any]] = None, started_ms: Optional[float] = None) -> None`
  - `graph_write(self, nodes: int = 0, rels: int = 0, labels: Optional[Dict[str, int]] = None) -> None`
- **with_job_context**  bases: ``
  - `__init__(self, job_id: Optional[str] = None, job_meta: Optional[Dict[str, Any]] = None)`
  - `__enter__(self)`
  - `__exit__(self, exc_type, exc, tb)`
**Functions**
- `_now_iso() -> str`
- `_redact(obj: Any) -> Any`
- `from_env(cls) -> 'Telemetry'`
- `enable_if_env(self) -> None`
- `_ensure_dirs(self) -> None`
- `_job_file(self, job_id: str) -> str`
- `_write(self, job_id: str, event: Dict[str, Any]) -> None`
- `start_job(self, job_id: Optional[str] = None, job_meta: Optional[Dict[str, Any]] = None) -> str`
- `end_job(self, status: str = 'ok', extra: Optional[Dict[str, Any]] = None) -> None`
- `llm_call(self, model: str, tokens_in: int, tokens_out: int, meta: Optional[Dict[str, Any]] = None) -> None`
- `reward(self, value: float, reason: str = '', meta: Optional[Dict[str, Any]] = None) -> None`
- `log_event(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> None`
- `tool_event(self, phase: str, name: str, args: Any = None, result: Any = None, ok: Optional[bool] = None, err: Optional[str] = None, extra: Optional[Dict[str, Any]] = None, started_ms: Optional[float] = None) -> None`
- `graph_write(self, nodes: int = 0, rels: int = 0, labels: Optional[Dict[str, int]] = None) -> None`
- `__init__(self, job_id: Optional[str] = None, job_meta: Optional[Dict[str, Any]] = None)`
- `__enter__(self)`
- `__exit__(self, exc_type, exc, tb)`
- `track_tool(name: Optional[str] = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]`
- `_decorator(fn: Callable[..., Any]) -> Callable[..., Any]`
- `_aw(*args, **kwargs)`
- `_sw(*args, **kwargs)`

### `D:\EcodiaOS\systems\simula\code_sim\archive\pareto.py`
**Functions**
- `_write_jsonl(obj: Dict)`
- `_read_jsonl() -> List[Dict]`
- `_dominates(a: Dict, b: Dict) -> bool`
- `add_candidate(record: Dict)`
- `top_k_similar(path: str, k: int = 3) -> List[Dict]`

### `D:\EcodiaOS\systems\simula\code_sim\evaluators\contracts.py`
**Functions**
- `_read(path: Path) -> str`
- `_approx_sig_present(src: str, func_sig: str) -> bool`
- `_contains_tool_registration(src: str, tool_name: str) -> bool`
- `_git_changed(sess) -> List[str]`
- `run(objective: dict, sandbox_session) -> Dict[str, object]`

### `D:\EcodiaOS\systems\simula\code_sim\evaluators\perf.py`
**Functions**
- `_is_mapping(x) -> bool`
- `_get(obj: Any, key: str, default = None)`
- `_get_path(obj: Any, path: Sequence[str], default = None)`
- `_extract_tests(step_or_objective: Any) -> List[str]`
- `_expand_tests(patterns: List[str]) -> List[str]`
- `_budget_seconds(objective: Any) -> float`
- `run(objective: dict, sandbox_session) -> Dict[str, Any]`

### `D:\EcodiaOS\systems\simula\code_sim\evaluators\runtime.py`
**Functions**
- `run(objective: dict, sandbox_session) -> dict`

### `D:\EcodiaOS\systems\simula\code_sim\evaluators\static.py`
**Functions**
- `_run(sess, args, timeout)`
- `run(step, sandbox_session) -> dict`

### `D:\EcodiaOS\systems\simula\code_sim\evaluators\tests.py`
**Functions**
- `_is_mapping(x) -> bool`
- `_get(obj: Any, key: str, default = None)`
- `_get_path(obj: Any, path: Sequence[str], default = None)`
- `_extract_tests(step_or_objective: Any) -> List[str]`
- `_expand_test_selection(patterns: List[str]) -> List[str]`
- `_coverage_per_file() -> Dict[str, float]`
- `_parse_counts(txt: str) -> Dict[str, int]`
- `_ratio(passed: int, total: int) -> float`
- `run(step_or_objective: Any, sandbox_session) -> Dict[str, Any]`

### `D:\EcodiaOS\systems\simula\code_sim\evaluators\__init__.py`
**Classes**
- **EvalResult** _(dataclass)_  bases: ``
  - `as_dict(self) -> Dict`
  - `unit_pass_ratio(self) -> float`
  - `integration_pass_ratio(self) -> float`
  - `static_score(self) -> float`
  - `security_score(self) -> float`
  - `contracts_score(self) -> float`
  - `perf_score(self) -> float`
  - `coverage_delta_score(self) -> float`
  - `policy_penalty(self) -> float`
  - `summary(self) -> Dict[str, Any]`
**Functions**
- `as_dict(self) -> Dict`
- `unit_pass_ratio(self) -> float`
- `integration_pass_ratio(self) -> float`
- `static_score(self) -> float`
- `security_score(self) -> float`
- `contracts_score(self) -> float`
- `perf_score(self) -> float`
- `coverage_delta_score(self) -> float`
- `policy_penalty(self) -> float`
- `summary(self) -> Dict[str, Any]`
- `run_evaluator_suite(objective: Dict[str, Any], sandbox_session) -> EvalResult`

### `D:\EcodiaOS\systems\simula\code_sim\mutators\ast_refactor.py`
**Classes**
- **AstMutator** _(dataclass)_  bases: ``
  - `set_aggressive(self, v: bool) -> None`
  - `mutate(self, step, mode: str = 'scaffold') -> Optional[str]`
  - `_do_scaffold(self, module: ast.Module, export_sig: Optional[str], step_name: str) -> bool`
  - `_do_imports(self, module: ast.Module) -> bool`
  - `_do_typing(self, module: ast.Module) -> bool`
  - `_do_error_paths(self, module: ast.Module) -> bool`
**Functions**
- `_read(path: Path) -> str`
- `_rel_for_diff(path: Path) -> str`
- `_unified_diff(old: str, new: str, rel_path: str) -> str`
- `_strip_shebang_and_encoding(src: str) -> Tuple[str, str]`
- `_ensure_module_docstring(tree: ast.Module, doc: str) -> None`
- `_parse_sig(signature: str) -> Tuple[str, List[str]]`
- `_build_func_def_from_sig(signature: str, doc: str) -> ast.FunctionDef`
- `_ensure_import(module: ast.Module, name: str, asname: Optional[str] = None, from_: Optional[str] = None) -> bool`
- `has_import() -> bool`
- `_ensure_logger(module: ast.Module) -> None`
- `_module_has_function(module: ast.Module, name: str) -> bool`
- `_add_guard_raises(fn: ast.FunctionDef, exc: str = 'ValueError') -> bool`
- `_ensure_return_annotations(fn: ast.FunctionDef) -> bool`
- `_ensure_arg_annotations(fn: ast.FunctionDef) -> bool`
- `set_aggressive(self, v: bool) -> None`
- `mutate(self, step, mode: str = 'scaffold') -> Optional[str]`
- `_do_scaffold(self, module: ast.Module, export_sig: Optional[str], step_name: str) -> bool`
- `_do_imports(self, module: ast.Module) -> bool`
- `_do_typing(self, module: ast.Module) -> bool`
- `_do_error_paths(self, module: ast.Module) -> bool`

### `D:\EcodiaOS\systems\simula\code_sim\mutators\prompt_patch.py`
**Functions**
- `_read_snip(p: Path, n: int = 120) -> str`
- `_targets_context(step: Any) -> str`
- `_strip_fences(text: Optional[str]) -> str`
- `llm_unified_diff(step: Any, variant: str = 'base') -> Optional[str]`

### `D:\EcodiaOS\systems\simula\code_sim\mutators\retrieval_edit.py`
**Functions**
- `_unidiff(old: str, new: str, rel: str) -> str`
- `_read(path: Path) -> str`
- `_ensure_line(src: str, needle: str) -> Tuple[str, bool]`
- `_detect_registry_path() -> Path`
- `retrieval_guided_edits(step, mode: Literal['registry', 'config', 'prior_art', 'tests']) -> Optional[str]`

### `D:\EcodiaOS\systems\simula\code_sim\mutators\__init__.py`

### `D:\EcodiaOS\systems\simula\code_sim\retrieval\context.py`
**Classes**
- **Neighbor** _(dataclass)_  bases: ``
**Functions**
- `default_neighbor_globs() -> List[str]`
- `_is_textual(path: Path) -> bool`
- `_shorten(text: str, limit: int) -> str`
- `_read_text(path: Path, limit: int = MAX_BYTES_PER_FILE) -> str`
- `_iter_globs(root: Path, patterns: Iterable[str]) -> Iterator[Path]`
- `_norm_rel(root: Path, p: Path) -> str`
- `_rank_neighbors(root: Path, primary: Path, candidates: Iterable[Path]) -> List[Neighbor]`
- `_pkg_root(p: Path) -> Optional[Path]`
- `_collect_candidates(root: Path, primary: Path) -> List[Path]`
- `_high_signal_slice(text: str, limit: int) -> str`
- `gather_neighbor_snippets(repo_root: Path, file_rel: str) -> Dict[str, str]`

### `D:\EcodiaOS\systems\simula\code_sim\sandbox\sandbox.py`
**Classes**
- **SandboxConfig** _(dataclass)_  bases: ``
- **AddOnlyApplyResult**  bases: `Tuple[bool, List[Path], Path]`
- **LocalSession**  bases: ``
  - `__init__(self, cfg: SandboxConfig)`
  - `run(self, cmd: List[str], timeout: int \| None = None) -> Tuple[int, str]`
  - `apply_unified_diff(self, diff: str) -> bool`
  - `revert(self) -> bool`
- **DockerSession**  bases: ``
  - `__init__(self, cfg: SandboxConfig)`
  - `_ensure_image_ready(self)`
  - `_docker_base(self, rw_repo: bool = False) -> List[str]`
  - `run(self, cmd: List[str], timeout: int \| None = None) -> Tuple[int, str]`
  - `apply_unified_diff(self, diff: str) -> bool`
  - `revert(self) -> bool`
  - `__del__(self)`
- **DockerSandbox**  bases: ``
  - `__init__(self, cfg_dict: Dict[str, object])`
  - `session(self)`
**Functions**
- `_merge_env(base: Dict[str, str], allow: Iterable[str], set_env: Dict[str, str]) -> Dict[str, str]`
- `_sanitize_llm_diff(diff_text: str, repo_root: Path) -> str`
- `_apply_add_only_diff_to_fs(diff_text: str, repo_root: Path) -> Tuple[bool, List[Path], Optional[Path], str]`
- `__init__(self, cfg: SandboxConfig)`
- `run(self, cmd: List[str], timeout: int \| None = None) -> Tuple[int, str]`
- `apply_unified_diff(self, diff: str) -> bool`
- `revert(self) -> bool`
- `__init__(self, cfg: SandboxConfig)`
- `_ensure_image_ready(self)`
- `_docker_base(self, rw_repo: bool = False) -> List[str]`
- `run(self, cmd: List[str], timeout: int \| None = None) -> Tuple[int, str]`
- `apply_unified_diff(self, diff: str) -> bool`
- `revert(self) -> bool`
- `__del__(self)`
- `__init__(self, cfg_dict: Dict[str, object])`
- `session(self)`

### `D:\EcodiaOS\systems\simula\code_sim\sandbox\seeds.py`
**Functions**
- `seed_config() -> Dict[str, object]`
- `ensure_toolchain(session) -> Dict[str, object]`

### `D:\EcodiaOS\systems\simula\code_sim\specs\schema.py`
**Classes**
- **Constraints** _(dataclass)_  bases: ``
  - `from_dict(d: Dict[str, Any] \| None) -> 'Constraints'`
- **UnitTestsSpec** _(dataclass)_  bases: ``
  - `from_dict(d: Dict[str, Any] \| None) -> 'UnitTestsSpec'`
- **ContractsSpec** _(dataclass)_  bases: ``
  - `from_dict(d: Dict[str, Any] \| None) -> 'ContractsSpec'`
- **DocsSpec** _(dataclass)_  bases: ``
  - `from_dict(d: Dict[str, Any] \| None) -> 'DocsSpec'`
- **PerfSpec** _(dataclass)_  bases: ``
  - `from_dict(d: Dict[str, Any] \| None) -> 'PerfSpec'`
- **AcceptanceSpec** _(dataclass)_  bases: ``
  - `from_dict(d: Dict[str, Any] \| None) -> 'AcceptanceSpec'`
- **RuntimeSpec** _(dataclass)_  bases: ``
  - `from_dict(d: Dict[str, Any] \| None) -> 'RuntimeSpec'`
- **Objective** _(dataclass)_  bases: ``
  - `from_dict(d: Dict[str, Any] \| None) -> 'Objective'`
  - `get(self, *path: str, default: Any = None) -> Any`
- **StepTarget** _(dataclass)_  bases: ``
  - `from_dict(d: Dict[str, Any]) -> 'StepTarget'`
- **Step** _(dataclass)_  bases: ``
  - `from_dict(d: Dict[str, Any]) -> 'Step'`
  - `primary_target(self) -> Tuple[Optional[str], Optional[str]]`
  - `acceptance(self) -> AcceptanceSpec`
  - `runtime(self) -> RuntimeSpec`
- **Plan** _(dataclass)_  bases: ``
**Functions**
- `from_dict(d: Dict[str, Any] \| None) -> 'Constraints'`
- `from_dict(d: Dict[str, Any] \| None) -> 'UnitTestsSpec'`
- `from_dict(d: Dict[str, Any] \| None) -> 'ContractsSpec'`
- `from_dict(d: Dict[str, Any] \| None) -> 'DocsSpec'`
- `from_dict(d: Dict[str, Any] \| None) -> 'PerfSpec'`
- `from_dict(d: Dict[str, Any] \| None) -> 'AcceptanceSpec'`
- `from_dict(d: Dict[str, Any] \| None) -> 'RuntimeSpec'`
- `from_dict(d: Dict[str, Any] \| None) -> 'Objective'`
- `get(self, *path: str, default: Any = None) -> Any`
- `from_dict(d: Dict[str, Any]) -> 'StepTarget'`
- `from_dict(d: Dict[str, Any]) -> 'Step'`
- `primary_target(self) -> Tuple[Optional[str], Optional[str]]`
- `acceptance(self) -> AcceptanceSpec`
- `runtime(self) -> RuntimeSpec`

### `D:\EcodiaOS\systems\simula\code_sim\utils\repo_features.py`
**Functions**
- `file_degree(rel: str, max_files: int = 20000) -> int`
- `file_churn(rel: str, days: int = 180) -> int`
- `plan_entropy(plan: List[Dict]) -> float`
- `features_for_file(job_meta: Dict, file_plan: Dict) -> Dict`

### `D:\EcodiaOS\systems\simula\policy\emit.py`
**Functions**
- `patch_to_policygraph(candidate: Dict[str, Any]) -> PolicyGraph`

### `D:\EcodiaOS\systems\simula\policy\effects.py`
**Classes**
- **EffectAnalyzer**  bases: `ast.NodeVisitor`
  - `__init__(self)`
  - `visit_Import(self, node: ast.Import)`
  - `visit_ImportFrom(self, node: ast.ImportFrom)`
  - `visit_Call(self, node: ast.Call)`
**Functions**
- `__init__(self)`
- `visit_Import(self, node: ast.Import)`
- `visit_ImportFrom(self, node: ast.ImportFrom)`
- `visit_Call(self, node: ast.Call)`
- `extract_effects_from_diff(diff_text: str) -> Dict[str, bool]`

### `D:\EcodiaOS\systems\simula\service\deps.py`
**Classes**
- **Settings**  bases: `BaseSettings`

### `D:\EcodiaOS\systems\simula\service\main.py`
**Functions**
- `root_ok()`

### `D:\EcodiaOS\systems\simula\service\routers\health.py`
**Functions**
- `health()`

### `D:\EcodiaOS\systems\simula\service\routers\jobs_codegen.py`
**Classes**
- **TargetHint** _(pydantic)_  bases: `BaseModel`
- **CodegenRequest** _(pydantic)_  bases: `BaseModel`
- **CodegenResponse** _(pydantic)_  bases: `BaseModel`
**Functions**
- `start_agent_job(req: CodegenRequest, response: Response) -> CodegenResponse`

### `D:\EcodiaOS\systems\simula\service\services\codegen.py`
**Classes**
- **JobContext**  bases: ``
  - `__init__(self, spec: str, targets: Optional[List[Dict[str, Any]]])`
  - `_utc_iso(self, ts: float) -> str`
  - `_write_json_atomic(self, path: Path, data: Dict[str, Any])`
  - `log_event(self, event_type: str, data: Optional[Dict[str, Any]] = None)`
  - `setup_logging(self)`
  - `teardown_logging(self)`
  - `finalize(self, status: str, notes: str, error: Optional[Exception] = None)`
**Functions**
- `__init__(self, spec: str, targets: Optional[List[Dict[str, Any]]])`
- `_utc_iso(self, ts: float) -> str`
- `_write_json_atomic(self, path: Path, data: Dict[str, Any])`
- `log_event(self, event_type: str, data: Optional[Dict[str, Any]] = None)`
- `setup_logging(self)`
- `teardown_logging(self)`
- `finalize(self, status: str, notes: str, error: Optional[Exception] = None)`
- `run_codegen_job(spec: str, targets: Optional[List[Dict[str, Any]]] = None, dry_run: bool = False) -> Dict[str, Any]`

### `D:\EcodiaOS\systems\simula\service\services\equor_bridge.py`
**Functions**
- `_current_identity_id() -> str`
- `fetch_identity_context(spec: str) -> Dict[str, Any]`
- `resolve_equor_for_agent(*_args, **_kwargs)`
- `log_call_result(*_args, **_kwargs)`

### `D:\EcodiaOS\systems\simula\service\services\executor.py`
**Functions**
- `run_cmd(cmd: Sequence[str], cwd: Optional[str] = None, timeout: Optional[int] = None) -> dict[str, Any]`

### `D:\EcodiaOS\systems\simula\service\services\prompts.py`
**Functions**
- `_read_file_snippet(path: Path, max_lines: int = 60) -> str`
- `_gather_repo_context(targets: List[Dict[str, Any]], max_lines: int = 60) -> str`
- `build_plan_prompt(spec: str, targets: List[Dict[str, Any]]) -> str`
- `build_file_prompt(spec: str, file_plan: Dict[str, Any]) -> str`

### `D:\EcodiaOS\systems\simula\service\services\vcs.py`
**Functions**
- `_git_sync(args: List[str], repo_path: str) -> Dict`
- `_git(args: List[str], repo_path: str) -> Dict`
- `ensure_branch(branch: str, repo_path: str)`
- `commit_all(repo_path: str, message: str)`

### `D:\EcodiaOS\workers\promoter.py`
**Functions**
- `run()`

### `D:\EcodiaOS\tools\hello.py`

### `D:\EcodiaOS\workspace\hello\src\sum2.py`

### `D:\EcodiaOS\workspace\hello\tests\test_sum2.py`
**Functions**
- `test_sum2()`

### `D:\EcodiaOS\src\sum2.py`

### `D:\EcodiaOS\src\simula\config.py`
**Classes**
- **GitSettings** _(pydantic)_  bases: `BaseModel`
- **AppSettings**  bases: `BaseSettings`
**Functions**
- `_load_config_from_yaml(env: str) -> dict`

### `D:\EcodiaOS\src\simula\git_manager.py`
**Classes**
- **GitError**  bases: `Exception`
  - `__init__(self, message: str, stdout: str, stderr: str, return_code: int)`
  - `__str__(self)`
- **GitManager**  bases: ``
  - `__init__(self, config: GitSettings)`
  - `_run_command(self, command: list[str], cwd: Optional[Path] = None) -> Tuple[str, str]`
  - `clone_or_pull(self)`
  - `reset_workspace(self)`
  - `apply_patch(self, patch_path: Path) -> str`
**Functions**
- `__init__(self, message: str, stdout: str, stderr: str, return_code: int)`
- `__str__(self)`
- `__init__(self, config: GitSettings)`
- `_run_command(self, command: list[str], cwd: Optional[Path] = None) -> Tuple[str, str]`
- `clone_or_pull(self)`
- `reset_workspace(self)`
- `apply_patch(self, patch_path: Path) -> str`

### `D:\EcodiaOS\src\simula\main.py`
**Functions**
- `_configure_logging() -> None`
- `_resolve_patch_path(cli_path: str \| None) -> Path`
- `_parse_args(argv: list[str]) -> argparse.Namespace`
- `main() -> None`

### `D:\EcodiaOS\src\src\simula_demo\__init__.py`

### `D:\EcodiaOS\src\src\simula_demo\hello_cli.py`

### `D:\EcodiaOS\src\src\simula_demo\math_utils.py`
**Functions**
- `add(a, b)`
- `fib(n)`

### `D:\EcodiaOS\DEcodiaOSsystemssimula\simula\common\string_utils.py`
**Functions**
- `reverse_string(s: str) -> str`

### `D:\EcodiaOS\DEcodiaOSsystemssimula\tests\test_string_utils.py`
**Functions**
- `test_reverse_string()`

### `D:\EcodiaOS\DEcodiaOSsystemssimula\tests\__init__.py`

### `D:\EcodiaOS\tests\__init__.py`

### `D:\EcodiaOS\tests\test_sim_orch.py`
**Functions**
- `test_orchestrator_run_follows_hot_path(MockSynapseClient, MockDockerSandbox, mock_generate_portfolio, mock_plan)`

### `D:\EcodiaOS\tests\test_port.py`
**Functions**
- `mock_eval_result()`
- `test_generate_portfolio_returns_full_list(mock_add_candidate, mock_run_suite, mock_generate, mock_eval_result)`

### `D:\EcodiaOS\tests\test_syn_clie.py`
**Functions**
- `mock_http_client()`
- `test_get_policy_hint(mock_http_client)`
- `test_ingest_reward(mock_http_client)`
