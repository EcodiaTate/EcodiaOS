from fastapi import APIRouter

from .annotate import annotate_router
from .arch_exec import arch_exec_router
from .auto_pipeline import auto_pipeline_router
from .bb import bb_router
from .cache_hygiene import cache_hygiene_router
from .catalog_admin import catalog_admin_router
from .codemod import codemod_router
from .coverage_quick import coverage_quick_router
from .dossier import dossier_router
from .gcb import gcb_router
from .git_ops import git_router
from .graph_export import graph_export_router
from .hygiene_check import hygiene_router
from .impact import impact_router
from .manifest import manifest_router
from .mutants import mutants_router
from .plan import plan_router
from .policy import policy_router
from .policypacks import policy_packs_router
from .pr_bundle import pr_bundle_router
from .proposal_verify import proposal_verify_router
from .pytest_parse import pytest_parse_router
from .quality import quality_router
from .recipes import recipes_router
from .rg_search import rg_router
from .safety_scans import safety_router
from .secrets_scan import secrets_scan_router
from .shadow_run import shadow_run_router
from .spec_eval import spec_eval_router
from .tools_catalog import catalogue_router
from .wm_admin import wm_admin_router
from .wm_search import wm_search_router
from .wm_symbols import wm_symbols_router
from .workspace_snapshot import workspace_router
from .xref import xref_router
from .code_graph import code_graph_router
from .services_api import constitution_router
from .conflict import conflicts_router
from .services_api import deliberation_router
from .services_api import learning_router

qora_router = APIRouter()
qora_router.include_router(code_graph_router, prefix="/code_graph")
qora_router.include_router(learning_router, prefix="/learning")
qora_router.include_router(arch_exec_router, prefix="/arch")
qora_router.include_router(gcb_router, prefix="/gcb")
qora_router.include_router(constitution_router, prefix="/constitution")
qora_router.include_router(deliberation_router, prefix="/deliberation")
qora_router.include_router(conflicts_router, prefix="/conflicts")
qora_router.include_router(manifest_router, prefix="/manifest")
qora_router.include_router(catalogue_router, prefix="/catalog")
qora_router.include_router(shadow_run_router, prefix="/shadow")
qora_router.include_router(spec_eval_router, prefix="/spec_eval")
qora_router.include_router(xref_router, prefix="/xref")
qora_router.include_router(secrets_scan_router, prefix="/secrets")
qora_router.include_router(wm_search_router, prefix="/wm")
qora_router.include_router(wm_admin_router, prefix="/wm_admin")
qora_router.include_router(wm_symbols_router, prefix="/wm_symbols")
qora_router.include_router(workspace_router, prefix="/workspace")
qora_router.include_router(safety_router, prefix="/safety")
qora_router.include_router(recipes_router, prefix="/recipes")
qora_router.include_router(quality_router, prefix="/quality")
qora_router.include_router(pytest_parse_router)
qora_router.include_router(proposal_verify_router)
qora_router.include_router(rg_router, prefix="/rg")
qora_router.include_router(bb_router, prefix="/bb")
qora_router.include_router(pr_bundle_router)
qora_router.include_router(policy_router, prefix="/policy")
qora_router.include_router(policy_packs_router, prefix="/policy_packs")
qora_router.include_router(plan_router, prefix="/plan")
qora_router.include_router(auto_pipeline_router)
qora_router.include_router(cache_hygiene_router, prefix="/cache_hygiene")
qora_router.include_router(annotate_router, prefix="/annotate")
qora_router.include_router(catalog_admin_router, prefix="/catalog_admin")
qora_router.include_router(codemod_router, prefix="/codemod")
qora_router.include_router(coverage_quick_router, prefix="/coverage_quick")
qora_router.include_router(dossier_router, prefix="/dossier")
qora_router.include_router(git_router, prefix="/git")
qora_router.include_router(mutants_router, prefix="/mutants")
qora_router.include_router(graph_export_router)
qora_router.include_router(hygiene_router, prefix="/hygiene")
qora_router.include_router(impact_router, prefix="/impact")
