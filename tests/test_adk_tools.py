from backend.app import adk_tools


def test_adk_tool_functions_are_callable_without_optional_runtime() -> None:
    assert callable(adk_tools.get_current_health_facts)
    assert callable(adk_tools.get_emergency_health_facts)
    assert callable(adk_tools.get_health_contradictions)
