def test_registry_has_callables():
    from systems.simula.agent.tool_registry import TOOLS

    assert isinstance(TOOLS, dict) and TOOLS
    missing = [k for k, v in TOOLS.items() if not callable(v)]
    assert not missing, f"Missing callables: {missing}"


def test_specs_and_impls_align():
    from systems.simula.agent.tool_registry import TOOLS
    from systems.simula.agent.tool_specs import get_tool_specs

    spec_names = {s["name"] for s in get_tool_specs()}
    impl_names = set(TOOLS.keys())
    # It’s fine to have extra impls; we just care about spec’d ones missing impls
    missing_impl = sorted(spec_names - impl_names)
    assert not missing_impl, f"Spec with no implementation: {missing_impl}"
