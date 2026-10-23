from app.services.supervisor_service import SupervisorService

def test_agent_trace_has_safe_supervisor_and_tool_entries():
    trace = SupervisorService._build_agent_trace(
        {"tool_trace": [{"tool": "repo_search", "status": "success", "summary": {"total_found": 2}}]}, 0.0
    )
    assert trace[0]["node"] == "supervisor"
    assert trace[1] == {"node": "tool", "tool": "repo_search", "status": "success", "result_summary": {"total_found": 2}}
