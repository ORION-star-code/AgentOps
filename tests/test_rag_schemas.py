import pytest
from pydantic import ValidationError

from agentops_api.rag import Citation, RagEvidence, RagHitStatus, RetrievedChunk


def test_valid_hit_rag_evidence() -> None:
    evidence = RagEvidence(
        query="What policy applies?",
        hit_status=RagHitStatus.HIT,
        chunks=[
            RetrievedChunk(
                chunk_id="chunk-1",
                source_uri="kb://policy/123",
                content_preview="The policy applies to enterprise users.",
                score=0.91,
            )
        ],
        citations=[
            Citation(
                chunk_id="chunk-1",
                claim="The policy applies to enterprise users.",
                quote="applies to enterprise users",
            )
        ],
        citation_coverage=1,
    )

    assert evidence.hit_status == RagHitStatus.HIT
    assert evidence.citations[0].chunk_id == "chunk-1"


def test_citation_must_reference_retrieved_chunk() -> None:
    with pytest.raises(ValidationError, match="unknown chunk_id"):
        RagEvidence(
            query="What policy applies?",
            hit_status=RagHitStatus.HIT,
            chunks=[
                RetrievedChunk(
                    chunk_id="chunk-1",
                    source_uri="kb://policy/123",
                    content_preview="The policy applies to enterprise users.",
                )
            ],
            citations=[Citation(chunk_id="missing-chunk")],
        )


def test_hit_requires_citation() -> None:
    with pytest.raises(ValidationError, match="requires at least one citation"):
        RagEvidence(
            query="What policy applies?",
            hit_status=RagHitStatus.HIT,
            chunks=[
                RetrievedChunk(
                    chunk_id="chunk-1",
                    source_uri="kb://policy/123",
                    content_preview="The policy applies to enterprise users.",
                )
            ],
            citations=[],
        )


def test_miss_allows_empty_chunks() -> None:
    evidence = RagEvidence(
        query="Unknown policy?",
        hit_status=RagHitStatus.MISS,
        chunks=[],
        citations=[],
    )

    assert evidence.chunks == []
    assert evidence.citations == []


def test_miss_rejects_citations() -> None:
    with pytest.raises(ValidationError, match="cannot include citations"):
        RagEvidence(
            query="Unknown policy?",
            hit_status=RagHitStatus.MISS,
            chunks=[
                RetrievedChunk(
                    chunk_id="chunk-1",
                    source_uri="kb://policy/123",
                    content_preview="The policy applies to enterprise users.",
                )
            ],
            citations=[Citation(chunk_id="chunk-1")],
        )
