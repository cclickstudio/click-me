# RAG 평가 — Hit Rate@k, MRR, Context Precision, Faithfulness(LLM as Judge)
"""KB 검색 품질을 정량 측정한다. 평가 순서: RAG 지표 ≥ 목표 → Faithfulness 측정.

목표 기준 (출처: 2025 프로덕션 RAG 가이드, RAGAS, FaithJudge EMNLP 2025):
  Hit Rate@5       ≥ 0.80  (Dextralabs 2025 프로덕션 기준선)
  MRR              ≥ 0.60  (LlamaIndex 실측 기준선 0.6206)
  Context Precision ≥ 0.75  (RAGAS 기준 0.80이 '노이즈 낮음')
  Faithfulness     ≥ 0.85  (FaithJudge: 최고 LLM 판사 인간 동의율 84%)

실행: cd backend && uv run python -m domain.management.assistant.rag_eval --k 5
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import select

from core.config import settings
from core.db import AsyncSessionLocal
from core.models import ManagementKbChunk, ManagementKbEvalCase
from domain.management.assistant.embeddings import build_embedding_provider
from domain.management.assistant.retriever import MANAGEMENT_SOURCE_TYPES, KbRetriever

# ── 프롬프트 템플릿 ──────────────────────────────────────────────────────────

_QA_PROMPT = """\
아래는 Meta 광고 운영 지식베이스의 한 청크입니다.
마케팅 매니저가 실제로 물어볼 법한 질문 1개를 한국어로 생성하세요.
- 이 청크의 내용만으로 답할 수 있어야 합니다.
- 청크 제목이나 문서 이름을 질문에 직접 언급하지 마세요.
- "~는 무엇인가요?" 보다 "~하면 어떻게 해야 하나요?" 형태를 선호합니다.

[청크]
{chunk}

질문:"""

_FAITHFULNESS_PROMPT = """\
[질문]
{question}

[에이전트 응답]
{answer}

[참조 문서 (KB 인용)]
{context}

위 응답이 참조 문서의 내용에 근거하고 있으면 'faithful', 문서에 없는 내용을 단정하거나 \
hallucination이 있으면 'not_faithful'로 평가하세요.
응답: faithful 또는 not_faithful (한 단어만)"""


# ── QA쌍 생성 ───────────────────────────────────────────────────────────────


async def generate_qa_pairs(limit: int = 50) -> int:
    """DB의 ManagementKbChunk를 순회하며 QA쌍 생성 후 ManagementKbEvalCase에 저장.

    이미 QA쌍이 있는 (source, title) 조합은 멱등 스킵.
    Returns: 새로 생성된 QA쌍 수.
    """
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    created = 0

    async with AsyncSessionLocal() as db:
        # 이미 생성된 (source, title) 조합 조회 — 중복 생성 방지
        existing_cases = (
            (
                await db.execute(
                    select(ManagementKbEvalCase).where(
                        ManagementKbEvalCase.expected_citations.isnot(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        existing: set[tuple[str, str]] = set()
        for case in existing_cases:
            if case.expected_citations:
                for ec in case.expected_citations:
                    existing.add((ec.get("source", ""), ec.get("title", "")))

        chunks = (
            (
                await db.execute(
                    select(ManagementKbChunk)
                    .order_by(ManagementKbChunk.source, ManagementKbChunk.chunk_index)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )

        for chunk in chunks:
            if (chunk.source, chunk.title) in existing:
                continue
            try:
                resp = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "user", "content": _QA_PROMPT.format(chunk=chunk.chunk[:1200])}
                    ],
                    temperature=0.3,
                    max_tokens=128,
                )
                question = resp.choices[0].message.content.strip()
                if not question:
                    continue
                db.add(
                    ManagementKbEvalCase(
                        id=uuid.uuid4(),
                        question=question,
                        expected_citations=[{"source": chunk.source, "title": chunk.title}],
                        fixture_version="rag_eval_v1",
                    )
                )
                created += 1
                print(f"  생성: [{chunk.source}] {chunk.title[:40]} -> {question[:60]}...")
            except Exception as e:  # noqa: BLE001
                print(f"  스킵: {chunk.title} - {e}")

        await db.commit()

    print(f"QA쌍 생성 완료: {created}건 신규")
    return created


# ── 평가 지표 계산 ───────────────────────────────────────────────────────────


def _match_rank(retrieved: list[dict], expected_citations: list[dict]) -> int | None:
    """정답 청크(source+title)가 retrieved에 있으면 1-indexed rank, 없으면 None."""
    gt_keys = {(ec["source"], ec.get("title", "")) for ec in expected_citations}
    for i, r in enumerate(retrieved):
        if (r["source"], r.get("title", "")) in gt_keys:
            return i + 1
    return None


def hit_rate(ranks: list[int | None]) -> float:
    """Hit Rate — 정답이 top-k 안에 있는 비율. rank=None이면 miss."""
    if not ranks:
        return 0.0
    return sum(1 for r in ranks if r is not None) / len(ranks)


def mrr(ranks: list[int | None]) -> float:
    """MRR — 정답 순위의 역수 평균. rank=None이면 0으로 처리."""
    if not ranks:
        return 0.0
    return sum(1.0 / r for r in ranks if r is not None) / len(ranks)


def context_precision(ranks: list[int | None]) -> float:
    """Context Precision — 정답이 상위에 있을수록 높음. Average Precision 방식.

    rank 1=1.0, rank 2=0.5, rank k=1/k. 없으면 0.
    """
    if not ranks:
        return 0.0
    return sum(1.0 / r for r in ranks if r is not None) / len(ranks)


# ── 전체 평가 실행 ───────────────────────────────────────────────────────────


async def evaluate(k: int = 5) -> dict[str, Any]:
    """저장된 QA쌍으로 Hit Rate@k + MRR + Context Precision 계산.

    Returns:
        {hit_rate_at_k, mrr, context_precision, n_cases, k, misses: [...]}
    """
    retriever = KbRetriever(embedder=build_embedding_provider(settings))

    async with AsyncSessionLocal() as db:
        cases = (
            (
                await db.execute(
                    select(ManagementKbEvalCase).where(
                        ManagementKbEvalCase.expected_citations.isnot(None)
                    )
                )
            )
            .scalars()
            .all()
        )

    if not cases:
        return {"error": "QA쌍 없음 — POST /kb/eval/generate 먼저 실행"}

    ranks: list[int | None] = []
    misses: list[str] = []

    for case in cases:
        try:
            # eval = management 특화 KB 품질 측정 → general_knowledge 제외(search_kb와 동일 스코프).
            hits = await retriever.search(case.question, k=k, source_types=MANAGEMENT_SOURCE_TYPES)
            rank = _match_rank(hits, case.expected_citations)
            ranks.append(rank if rank is not None and rank <= k else None)
            if rank is None or rank > k:
                misses.append(case.question[:80])
        except Exception as e:  # noqa: BLE001 — 개별 실패는 전체 평가 안 막음
            ranks.append(None)
            misses.append(f"[오류] {case.question[:60]}: {e}")

    return {
        "hit_rate_at_k": round(hit_rate(ranks), 4),
        "mrr": round(mrr(ranks), 4),
        "context_precision": round(context_precision(ranks), 4),
        "n_cases": len(cases),
        "k": k,
        "n_miss": len(misses),
        "misses": misses[:5],  # 최대 5건만 반환
        "targets": {"hit_rate": 0.80, "mrr": 0.60, "context_precision": 0.75},
    }


# ── Faithfulness 평가 (LLM as Judge) ─────────────────────────────────────────


async def evaluate_faithfulness(n: int = 30) -> dict[str, Any]:
    """저장된 QA쌍 n개를 에이전트에 질의 → faithfulness 측정 (LLM as Judge).

    사전 조건: evaluate()의 hit_rate_at_5 ≥ 0.80 달성 후 실행.
    Returns:
        {faithfulness, n_cases, not_faithful_examples: [...]}
    """
    from domain.management.assistant.retriever import KbRetriever  # noqa: PLC0415

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    retriever = KbRetriever(embedder=build_embedding_provider(settings))

    async with AsyncSessionLocal() as db:
        cases = (
            (
                await db.execute(
                    select(ManagementKbEvalCase)
                    .where(ManagementKbEvalCase.expected_citations.isnot(None))
                    .limit(n)
                )
            )
            .scalars()
            .all()
        )

    if not cases:
        return {"error": "QA쌍 없음 — POST /kb/eval/generate 먼저 실행"}

    faithful_count = 0
    error_count = 0
    not_faithful_examples: list[dict] = []

    for case in cases:
        try:
            # KB 검색 → 컨텍스트 구성 (management 특화 스코프 — search_kb와 동일)
            hits = await retriever.search(case.question, k=3, source_types=MANAGEMENT_SOURCE_TYPES)
            context = "\n\n".join(h["chunk"][:400] for h in hits) if hits else "(검색 결과 없음)"

            # GPT-4o-mini로 답변 생성
            ans_resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "당신은 Meta 광고 운영 전문 어시스턴트입니다."
                            " 아래 참조 문서만 사용해 답하세요."
                        ),
                    },
                    {"role": "user", "content": f"[참조]\n{context}\n\n[질문]\n{case.question}"},
                ],
                temperature=0.0,
                max_tokens=256,
            )
            answer = ans_resp.choices[0].message.content.strip()

            # LLM as Judge — Gemini 사용 (OpenAI 답변 생성과 judge 분리).
            # gemini-2.0-flash-lite는 2026 단종(404) → 현행 gemini-2.5-flash-lite로 교체.
            import google.generativeai as genai  # noqa: PLC0415

            genai.configure(api_key=settings.gemini_api_key or "")
            judge_model = genai.GenerativeModel("gemini-2.5-flash-lite")
            judge_resp_raw = judge_model.generate_content(
                _FAITHFULNESS_PROMPT.format(question=case.question, answer=answer, context=context),
                generation_config={"temperature": 0.0, "max_output_tokens": 10},
            )
            verdict = (judge_resp_raw.text or "").strip().lower()
            if "faithful" in verdict and "not" not in verdict:
                faithful_count += 1
            else:
                if len(not_faithful_examples) < 3:
                    not_faithful_examples.append(
                        {"question": case.question[:80], "answer": answer[:120]}
                    )
        except Exception as e:  # noqa: BLE001
            # 오류는 not_faithful로 보수 처리 — judge 고장(모델 단종 등)이 가짜 고득점으로
            # 가려지지 않게 한다. 과거 'faithful 처리'가 죽은 judge의 1.00을 만들었다.
            error_count += 1
            print(f"  판단 오류(not_faithful 처리): {e}")

    return {
        "faithfulness": round(faithful_count / len(cases), 4),
        "n_cases": len(cases),
        "n_error": error_count,  # judge 호출 실패 수 — >0이면 측정 신뢰 불가(고장 신호)
        "not_faithful_examples": not_faithful_examples,
        "target": 0.85,
    }


# ── CLI 실행 ─────────────────────────────────────────────────────────────────


async def _main(k: int) -> None:
    print(f"\n=== RAG 평가 (k={k}) ===")
    result = await evaluate(k=k)
    if "error" in result:
        print(result["error"])
        return
    targets = result["targets"]
    hr = result["hit_rate_at_k"]
    m = result["mrr"]
    cp = result["context_precision"]
    hr_ok = "✅" if hr >= targets["hit_rate"] else "❌"
    mrr_ok = "✅" if m >= targets["mrr"] else "❌"
    cp_ok = "✅" if cp >= targets["context_precision"] else "❌"
    print(f"Hit Rate@{k}:        {hr:.4f}  {hr_ok} (목표 {targets['hit_rate']})")
    print(f"MRR:               {m:.4f}  {mrr_ok} (목표 {targets['mrr']})")
    print(f"Context Precision: {cp:.4f}  {cp_ok} (목표 {targets['context_precision']})")
    print(f"케이스 수: {result['n_cases']}, 미스: {result['n_miss']}")
    if result["misses"]:
        print("미스 질문 (최대 5):")
        for q in result["misses"]:
            print(f"  - {q}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--generate", action="store_true", help="QA쌍 먼저 생성")
    args = parser.parse_args()
    if args.generate:
        asyncio.run(generate_qa_pairs())
    asyncio.run(_main(args.k))
