# systems/synapse/firewall/smt_guard.py
# FINAL VERSION FOR PHASE III
from __future__ import annotations

from systems.synapse.policy.policy_dsl import PolicyGraph


def check_smt_constraints(policy: PolicyGraph) -> tuple[bool, str]:
    """
    Validates a policy graph against its SMT constraints.
    This version simulates a more advanced prover by checking for multiple dangerous patterns.
    """
    danger_constraints = [c for c in policy.constraints if c.constraint_class == "danger"]
    if not danger_constraints:
        return True, "OK (No danger constraints)"

    all_effects = {effect for node in policy.nodes for effect in node.effects}

    for constraint in danger_constraints:
        # Check for Write + Network Access Concurrency
        if constraint.smt_expression == "(not (and write net_access))":
            if "write" in all_effects and "net_access" in all_effects:
                reason = "SMT Block: Policy combines 'write' and 'net_access' effects, which is forbidden."
                print(f"[SMT-Guard] {reason}")
                return False, reason

        # Check for Execute + State Change Concurrency
        if constraint.smt_expression == "(not (and execute state_change))":
            if "execute" in all_effects and "state_change" in all_effects:
                reason = "SMT Block: Policy combines 'execute' and 'state_change' effects, which is a high-risk operation."
                print(f"[SMT-Guard] {reason}")
                return False, reason

    return True, "OK (SMT Validated)"
