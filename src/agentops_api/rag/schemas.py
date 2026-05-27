"""RAG retrieval evidence schemas."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agentops_api.observability.schemas import JsonObject, validate_json_size


class RagHitStatus(StrEnum):
    """Retrieval quality signal for one RAG query."""

    HIT = "hit"
    PARTIAL = "partial"
    MISS = "miss"


class RetrievedChunk(BaseModel):
    """One chunk returned by a retriever."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=1, max_length=300)
    source_uri: str = Field(min_length=1, max_length=2000)
    content_preview: str = Field(min_length=1, max_length=4000)
    score: float | None = None
    rerank_score: float | None = None
    metadata: JsonObject = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def metadata_must_fit(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_json_size(value)


class Citation(BaseModel):
    """A claim-to-chunk citation emitted or inferred for an answer."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=1, max_length=300)
    claim: str | None = Field(default=None, max_length=4000)
    quote: str | None = Field(default=None, max_length=4000)


class RagEvidence(BaseModel):
    """Structured evidence for one RAG retrieval step."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=4000)
    hit_status: RagHitStatus
    chunks: list[RetrievedChunk] = Field(default_factory=list, max_length=100)
    citations: list[Citation] = Field(default_factory=list, max_length=100)
    citation_coverage: float | None = Field(default=None, ge=0, le=1)
    metadata: JsonObject = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def metadata_must_fit(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_json_size(value)

    @model_validator(mode="after")
    def evidence_must_be_consistent(self) -> RagEvidence:
        chunk_ids = {chunk.chunk_id for chunk in self.chunks}
        citation_chunk_ids = {citation.chunk_id for citation in self.citations}
        missing_chunk_ids = citation_chunk_ids - chunk_ids
        if missing_chunk_ids:
            missing = ", ".join(sorted(missing_chunk_ids))
            raise ValueError(f"citations reference unknown chunk_id values: {missing}")

        if self.hit_status == RagHitStatus.HIT and not self.citations:
            raise ValueError("hit RAG evidence requires at least one citation")
        if self.hit_status == RagHitStatus.HIT and not self.chunks:
            raise ValueError("hit RAG evidence requires at least one retrieved chunk")
        if self.hit_status == RagHitStatus.PARTIAL and not self.chunks:
            raise ValueError("partial RAG evidence requires at least one retrieved chunk")
        if self.hit_status == RagHitStatus.MISS and self.citations:
            raise ValueError("miss RAG evidence cannot include citations")

        return self
