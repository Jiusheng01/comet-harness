"""Persona prompt optimization request/response schema."""
from pydantic import BaseModel, Field


class PersonaOptimizeRequest(BaseModel):
    system_prompt: str = Field(min_length=1, max_length=4000)
