from app.agents.llm_contracts import LLMRequest, SYSTEM_INSTRUCTIONS


def test_llm_contracts_define_evidence_boundary_for_all_specialists():
    assert set(SYSTEM_INSTRUCTIONS) == {"course_info", "academic_rules", "schedule_workload", "planner"}
    request = LLMRequest("course_info", "DSC4070 是什么课", [], SYSTEM_INSTRUCTIONS["course_info"])
    assert "官方课程证据" in request.system_instruction
