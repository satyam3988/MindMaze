from abc import ABC, abstractmethod

from pydantic import BaseModel


class LLMProvider(ABC):
    name: str
    model: str

    @abstractmethod
    async def generate(self, purpose: str, context: dict, schema: type[BaseModel]) -> BaseModel:
        """Return validated structured product state; never hidden reasoning."""
