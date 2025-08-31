# systems/equor/core/identity/constitution.py
from typing import Any

# P1 UPGRADE: Use a safe expression evaluation library instead of eval()
from asteval import Interpreter


class ConstitutionConflictError(Exception):
    """Custom exception raised when two or more active rules conflict."""

    def __init__(self, message: str, conflicting_rules: list[dict[str, Any]]):
        self.message = message
        self.conflicting_rules = conflicting_rules
        super().__init__(self.message)


class PredicateUnsatisfiedError(Exception):
    """Custom exception for when a machine-checkable rule predicate is not met."""

    def __init__(self, message: str, failing_rule: dict[str, Any]):
        self.message = message
        self.failing_rule = failing_rule
        super().__init__(self.message)


class ConstitutionService:
    """H5 Constitution Service with a formal predicate checker."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # P1 UPGRADE: Initialize the safe evaluator
            cls._instance.aeval = Interpreter()
        return cls._instance

    def _evaluate_predicate(self, predicate: str, context: dict[str, Any]) -> bool:
        """
        A safe evaluator for the rule DSL using the 'asteval' library.
        """
        try:
            # Add the context to the symbol table for the evaluator
            self.aeval.symtable["context"] = context
            return self.aeval.eval(predicate)
        except Exception as e:
            print(f"[Equor-SAT] Predicate evaluation failed for '{predicate}': {e}")
            return False  # Fail-closed: if a predicate can't be evaluated, it's considered not met.

    def check_formal_guards(self, rules: list[dict[str, Any]], context: dict[str, Any]):
        """
        Runs pre-composition satisfiability checks for all rules with a DSL predicate.
        """
        for rule in rules:
            predicate = rule.get("predicate_dsl")
            if predicate:
                is_satisfied = self._evaluate_predicate(predicate, context)
                if not is_satisfied:
                    message = f"Formal guard failed for rule '{rule['name']}': Predicate '{predicate}' was not satisfied by the context."
                    raise PredicateUnsatisfiedError(message, failing_rule=rule)
        print("[Equor-SAT] All formal guards satisfied.")

    def apply_precedence(self, rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Sorts a list of rules according to the system's precedence logic."""
        severity_map = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        return sorted(
            rules,
            key=lambda rule: (
                -rule.get("priority", 0),
                -severity_map.get(rule.get("severity", "low"), 0),
                rule.get("version", "0.0.0"),
            ),
            reverse=True,
        )

    def check_for_conflicts(self, rules: list[dict[str, Any]]) -> None:
        """Checks for direct, unresolved conflicts within a set of active rules."""
        rule_ids = {rule["id"] for rule in rules}
        rule_map = {rule["id"]: rule for rule in rules}

        for rule in rules:
            declared_conflicts = rule.get("conflicts_with", [])
            for conflicting_id in declared_conflicts:
                if conflicting_id in rule_ids:
                    conflicting_pair = [rule, rule_map[conflicting_id]]
                    message = (
                        f"Unresolved constitutional conflict detected. "
                        f"Rule '{rule['name']}' (ID: {rule['id']}) conflicts with "
                        f"Rule '{rule_map[conflicting_id]['name']}' (ID: {conflicting_id})."
                    )
                    raise ConstitutionConflictError(message, conflicting_rules=conflicting_pair)
