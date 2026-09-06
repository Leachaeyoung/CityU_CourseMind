"""OpenAI-compatible answer synthesis for CourseMind."""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import Optional
from urllib import error, request

from .llm_contracts import LLMRequest, LLMResponse


class LLMProviderError(RuntimeError):
    pass


class OpenAICompatibleProvider:
    def __init__(self) -> None:
        self.api_key = os.getenv("LLM_API_KEY", "").strip()
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com").rstrip("/")
        self.model = os.getenv("LLM_MODEL", "deepseek-v4-flash").strip()

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    def complete(self, request_data: LLMRequest) -> LLMResponse:
        if not self.configured:
            raise LLMProviderError("LLM 配置不完整")
        evidence = [asdict(item) if hasattr(item, "__dataclass_fields__") else dict(item) for item in request_data.evidence]
        prompt = ("先理解用户真正询问的字段，只回答问题所需的信息，不要罗列无关课程或字段。"
                  "如果用户只输入课程代码，则给出简洁课程概览，并在结构化事实包含 term_schedule 时一并概括该学期的 Section/CRN/时间/地点。"
                  "回答使用清晰的短标题和项目符号分组，不要写成一大段话。"
                  "只能使用下面提供的官方证据和结构化事实；结构化事实中的具体字段（例如地点、时间、CRN）必须优先采用。"
                  "如果结构化事实包含 eligibility_result，必须直接依据其 eligible 字段给出可以或不能选的确定结论。"
                  "除非用户明确要求依据或来源，否则不要主动解释证据。"
                  "证据不足时明确说明，不能猜测。\n\n"
                  f"用户问题：{request_data.user_message}\n负责 Agent：{request_data.agent}\n"
                  f"官方证据：{json.dumps(evidence, ensure_ascii=False)}")
        payload = {"model": self.model, "temperature": 0.2, "messages": [
            {"role": "system", "content": request_data.system_instruction},
            {"role": "user", "content": prompt},
        ]}
        req = request.Request(f"{self.base_url}/chat/completions",
                              data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                              headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                              method="POST")
        try:
            with request.urlopen(req, timeout=45) as response:
                data = json.loads(response.read().decode("utf-8"))
            text = data["choices"][0]["message"]["content"]
        except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError(f"大模型请求失败：{exc}") from exc
        usage = data.get("usage") or {}
        return LLMResponse(text=str(text), model=str(data.get("model") or self.model),
                           input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"))


def synthesize_answer(agent: str, user_message: str, evidence: list[dict], facts: Optional[dict] = None) -> dict:
    provider = OpenAICompatibleProvider()
    if not provider.configured:
        return {"llm_used": False, "answer": None, "llm_error": "未配置大模型 API"}
    try:
        context = list(evidence)
        context.append({"source_type": "structured_facts", "facts": facts or {}})
        response = provider.complete(LLMRequest(
            agent=agent, user_message=user_message, evidence=context,
            system_instruction=("你是 CourseMind 的回答生成器。先理解用户语意，只回答用户实际询问的内容，避免附带无关信息。"
                                "只根据官方证据和结构化事实回答，直接给出简洁、结构化的答案。"
                                "课表详情请提示用户以 AIMS 系统实际显示为准，不要使用‘快照’一词。"),
        ))
        return {"llm_used": True, "answer": response.text, "llm_model": response.model,
                "llm_usage": {"input_tokens": response.input_tokens, "output_tokens": response.output_tokens}}
    except LLMProviderError as exc:
        return {"llm_used": False, "answer": None, "llm_error": str(exc)}
