import json
import logging
import time

from openai import AsyncOpenAI

from robotic_mind.domain.models import now
from robotic_mind.llm.base import LLMProvider

log = logging.getLogger("robotic_mind.llm")


class NebiusNemotronProvider(LLMProvider):
    name = "Nebius Token Factory"

    def __init__(self, settings):
        self.model = settings.nebius_model
        self.client = AsyncOpenAI(
            api_key=settings.nebius_api_key,
            base_url=settings.nebius_base_url,
            timeout=60,
            max_retries=1,
        )
        self.last_request = None

    async def generate(self, purpose, context, schema):
        started = time.perf_counter()
        instructions = {
            "understand": "Interpret the user's red-object search. Reject unsupported requests.",
            "plan": "Assign every supplied region exactly once to an eligible supplied agent. "
            "Balance workload using positions and shared knowledge. Agents can have "
            "multiple regions. Never create regions or agents.",
            "synthesize": (
                "Summarize only the supplied Group Mind facts. Copy numeric facts exactly."
            ),
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "You coordinate Robotic Mind. Return one JSON object matching the schema. "
                    "Do not return reasoning, markdown or hidden chain of thought. "
                    + instructions[purpose]
                    + " Schema: "
                    + json.dumps(schema.model_json_schema())
                ),
            },
            {"role": "user", "content": json.dumps(context)},
        ]
        error = None
        for attempt in range(2):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    max_tokens=4096,
                )
                value = schema.model_validate_json(response.choices[0].message.content or "")
                self.last_request = {
                    "model": self.model,
                    "purpose": purpose,
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                    "timestamp": now(),
                    "attempts": attempt + 1,
                }
                log.info("LLM %s %s", self.name, self.last_request)
                return value
            except Exception as exc:
                error = exc
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "The response or request failed. Return valid JSON matching the schema."
                        ),
                    }
                )
        raise ValueError(f"Nebius {purpose} failed after two attempts ({type(error).__name__})")
