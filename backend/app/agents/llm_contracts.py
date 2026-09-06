"""Provider-neutral contracts for LLM answer synthesis."""
from dataclasses import dataclass
from typing import Mapping, Optional, Protocol, Sequence


@dataclass(frozen=True)
class LLMRequest:
    agent: str
    user_message: str
    evidence: Sequence[Mapping]
    system_instruction: str


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


class LLMProvider(Protocol):
    def complete(self, request: LLMRequest) -> LLMResponse:
        """Generate text only from the supplied evidence contract."""


SYSTEM_INSTRUCTIONS = {
    "course_info": "只依据官方课程证据回答；不确定时明确说明，不得编造课程内容或评估比例。",
    "academic_rules": "只依据对应 catalogue year 的官方培养方案和确定性规则回答。",
    "schedule_workload": "只依据目标学期 AIMS Section 证据回答；快照不得表述为实时可注册状态。",
    "planner": "先遵守硬约束，再解释软排序；不得用社区评价覆盖官方规则。",
}
