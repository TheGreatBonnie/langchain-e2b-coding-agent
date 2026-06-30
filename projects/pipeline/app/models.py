"""Pydantic models for request/response schemas."""

from pydantic import BaseModel, Field
from typing import Optional


class StoryResponse(BaseModel):
    id: int
    title: str
    url: Optional[str] = None
    score: int
    by: str
    time: int
    descendants: int = 0
    summary: Optional[str] = None
    fetched_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"from_attributes": True}


class PipelineResult(BaseModel):
    fetched: int = Field(..., description="Number of stories fetched from HN")
    summarized: int = Field(..., description="Number of stories summarized by LLM")
