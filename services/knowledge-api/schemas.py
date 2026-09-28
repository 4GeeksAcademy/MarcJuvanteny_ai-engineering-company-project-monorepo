from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str


class QueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
