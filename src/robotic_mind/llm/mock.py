from robotic_mind.llm.base import LLMProvider


class MockLLMProvider(LLMProvider):
    name = "Development mock"
    model = "deterministic-mock"

    async def generate(self, purpose, context, schema):
        if purpose == "understand":
            command = context["command"].lower()
            if "red" not in command or not any(w in command for w in ["find", "search", "locate"]):
                raise ValueError("This MVP supports searching for red objects only")
            return schema.model_validate(
                {
                    "objective": "find_objects",
                    "target": {"property": "color", "value": "red"},
                    "strategy": "parallel_search",
                    "constraints": ["avoid_duplicate_search"],
                    "completion_condition": "all_regions_searched",
                }
            )
        if purpose == "plan":
            agents = sorted(context["agents"], key=lambda agent: agent["agent_id"])
            if not agents:
                raise ValueError("No online robots support camera, navigate and detect_color")
            return schema.model_validate(
                {
                    "assignments": [
                        {"agent_id": agents[i % len(agents)]["agent_id"], "region": r["id"]}
                        for i, r in enumerate(context["regions"])
                    ]
                }
            )
        facts = context["facts"]
        return schema.model_validate(
            {
                **facts,
                "summary": (
                    f"Search complete. {facts['unique_objects']} unique red objects confirmed; "
                    f"{facts['regions_cleared']} sectors cleared. "
                    "Shared knowledge is saved in Group Mind."
                ),
            }
        )
