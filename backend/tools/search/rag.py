"""RAG 검색 툴 — pgvector 기반 유사 광고 검색 (A/B 비교, 7.8 목표)."""

from langchain_core.tools import tool
from openai import AsyncOpenAI
from sqlalchemy import text

from core.db import AsyncSessionLocal

client = AsyncOpenAI()


async def _embed(text_content: str) -> list[float]:
    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=text_content,
    )
    return response.data[0].embedding


@tool
async def search_similar_ads(query: str, top_k: int = 5) -> list[dict]:
    """광고 설명을 임베딩하여 pgvector로 유사 광고를 검색합니다.

    Args:
        query: 검색할 광고 내용 또는 키워드
        top_k: 반환할 유사 광고 수

    Returns:
        유사도 순으로 정렬된 광고 목록
    """
    embedding = await _embed(query)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT ad_id, content, 1 - (embedding <=> :embedding::vector) AS similarity
                FROM ad_embeddings
                ORDER BY embedding <=> :embedding::vector
                LIMIT :top_k
                """
            ),
            {"embedding": embedding, "top_k": top_k},
        )
        return [dict(row) for row in result.mappings()]
