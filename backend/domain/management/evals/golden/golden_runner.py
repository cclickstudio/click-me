# 통합 골든셋 러너 — 검색은 프로덕션 리트리버, 생성은 실제 CLIO 그래프(build_graph)로 측정.
# 사용: uv run python golden_runner.py <single|complex> [--limit N]
#  검색: Hit@5·MRR(다중소스 valid_sources, base vs LLM 리랭크), Context Precision(LLM 관련성 AP)
#  생성: 실제 ReAct 그래프 답변으로 Faithfulness(문맥 근거)·
#        Factual Correctness(gold 대비, before/after)
# judge×3 과반, 채점자 gpt-4o-mini(자기채점 편향 한계는 리포트에 명시).
import argparse
import asyncio
import contextlib
import json
import re
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI

from core.config import settings
from domain.management.assistant.embeddings import build_embedding_provider
from domain.management.assistant.graph import build_graph
from domain.management.assistant.retriever import MANAGEMENT_SOURCE_TYPES, KbRetriever

GOLD_DIR = Path("domain/management/evals/golden")
POOL = 12  # --pool로 오버라이드
JUDGE_MODEL = "gpt-4o-mini"
# 판사(채점자) 계열 — openai(gpt-4o-mini, 기본) | gemini(자기채점 편향 제거용, 무료쿼터 회복 시).
# 무료 티어 여유를 위해 flash-lite. 풀 품질을 원하면 GEMINI_JUDGE_MODEL을 gemini-2.5-flash로.
JUDGE_PROVIDER = "openai"
GEMINI_JUDGE_MODEL = "gemini-2.5-flash-lite"
client = AsyncOpenAI(api_key=settings.openai_api_key)
_gemini = None


def _get_gemini() -> Any:
    global _gemini
    if _gemini is None:
        import google.generativeai as genai  # 기존 rag_eval.py와 동일 SDK

        genai.configure(api_key=settings.gemini_api_key or "")
        _gemini = genai.GenerativeModel(GEMINI_JUDGE_MODEL)
    return _gemini


def load_set(which: str) -> list[dict]:
    """단일셋·복합셋 로드 → 공통 스키마. 두 파일 모두 valid_sources 인라인(자기완결)."""
    fname = "golden_set_complex.json" if which == "complex" else "golden_set.json"
    data = json.loads((GOLD_DIR / fname).read_text(encoding="utf-8"))
    for it in data:
        it.setdefault("valid_sources", [it["gold_source"]])
    return data


async def chat(prompt: str, mx: int = 60) -> str:
    r = await client.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=mx,
    )
    return r.choices[0].message.content or ""


async def jchat(prompt: str, mx: int = 20) -> str:
    """판사 전용 채팅 — JUDGE_PROVIDER에 따라 gpt-4o-mini(기본) 또는 Gemini(분리 채점).

    생성기(gpt-4o-mini)와 다른 계열로 채점해 자기채점 편향을 제거하는 용도. rerank·before는
    시스템/베이스라인이라 계속 OpenAI(chat)를 쓰고, Faithfulness·FC·Context Precision
    판정만 이 경로.
    """
    if JUDGE_PROVIDER == "gemini":

        def _call() -> str:
            r = _get_gemini().generate_content(
                prompt, generation_config={"temperature": 0.0, "max_output_tokens": mx}
            )
            return r.text or ""

        return await asyncio.to_thread(_call)
    return await chat(prompt, mx)


def _arr(t: str) -> list:
    m = re.search(r"\[.*\]", t, re.DOTALL)
    try:
        return json.loads(m.group(0)) if m else []
    except json.JSONDecodeError:
        return []


def _score(t: str) -> float:
    m = re.search(r'"?score"?\s*[:=]\s*([0-9.]+)', t)
    if not m:
        return 0.0
    v = float(m.group(1))
    return v if v in (0.0, 0.5, 1.0) else (1.0 if v > 0.75 else 0.5 if v > 0.25 else 0.0)


async def _vote(prompt: str, n: int = 3) -> float:
    """judge×n 과반/평균 — 0/0.5/1 중 다수값(동수면 평균). 판사=jchat(계열 분리 가능)."""
    scores = await asyncio.gather(*[jchat(prompt, 20) for _ in range(n)])
    vals = [_score(s) for s in scores]
    # 다수결: 최빈값
    from collections import Counter

    c = Counter(vals)
    top, cnt = c.most_common(1)[0]
    if cnt > n // 2:
        return top
    return round(sum(vals) / len(vals), 3)


def _hit_mrr(sources: list[str], valid: set[str]) -> tuple[int, float]:
    rank = next((i + 1 for i, s in enumerate(sources[:5]) if s in valid), 0)
    return (1 if rank else 0, (1.0 / rank) if rank else 0.0)


async def rerank(q: str, chunks: list[dict]) -> list[dict]:
    listing = "\n".join(f"[{i}] ({c['source']}) {c['chunk'][:160]}" for i, c in enumerate(chunks))
    order = [
        i
        for i in _arr(
            await chat(
                f"질문에 답하는 데 유용한 순서로 재정렬해 인덱스 배열만 JSON.\n질문:{q}\n{listing}",
                60,
            )
        )
        if isinstance(i, int) and 0 <= i < len(chunks)
    ]
    order += [i for i in range(len(chunks)) if i not in order]
    return [chunks[i] for i in order]


async def context_precision(q: str, top: list[dict]) -> float:
    """LLM 관련성 라벨(각 청크 1/0) → Average Precision. MRR 아닌 진짜 CP."""
    listing = "\n".join(f"[{i}] {c['chunk'][:160]}" for i, c in enumerate(top))
    rel = _arr(
        await jchat(
            f"각 문서가 질문에 관련 있으면 1 없으면 0. 길이 {len(top)} JSON 배열만."
            f"\n질문:{q}\n{listing}",
            40,
        )
    )
    rel = [1 if (i < len(rel) and rel[i] in (1, 1.0, True)) else 0 for i in range(len(top))]
    if not sum(rel):
        return 0.0
    h = 0.0
    ap = 0.0
    for i, x in enumerate(rel, 1):
        if x:
            h += 1
            ap += h / i
    return ap / sum(rel)


async def faith_judge(ctx: str, ans: str) -> float:
    return await _vote(
        f"[참조]\n{ctx[:1600]}\n[답변]\n{ans}\n"
        f"답변의 주장이 참조에 근거하면 1.0, 일부 근거 없음 0.5, "
        f'참조와 모순/날조 0.0. JSON {{"score":1.0}}만.'
    )


async def fc_judge(gold: str, ans: str) -> float:
    return await _vote(
        f"[정답]\n{gold}\n[답변]\n{ans}\n"
        f"답변이 정답과 핵심 사실이 일치하면 1.0, 일부 누락/불명확 0.5, "
        f'모순/틀림 0.0. 표현 차이는 감점 아님. JSON {{"score":1.0}}만.'
    )


def build_agent_graph():
    """실제 CLIO 그래프 — 프로덕션 build_graph 그대로(gpt-4o-mini + 실 임베딩 리트리버).

    live_* 툴이 실제 Meta를 치지 않도록 reader만 mock 강제(임베딩·LLM·KB는 실연동 유지).
    질문이 KB용이라 대부분 search_kb만 쓰지만, 에이전트가 live 툴을 부를 때의 안전장치.
    """
    from langgraph.checkpoint.memory import MemorySaver

    # frozen settings면 무시(질문이 KB용이라 위험 낮음)
    with contextlib.suppress(Exception):
        settings.management_reader_mock = True
    model = getattr(settings, "management_assistant_model", "gpt-4o-mini")
    llm = ChatOpenAI(model=model, temperature=0.0, api_key=settings.openai_api_key)
    retriever = KbRetriever(embedder=build_embedding_provider(settings))
    return build_graph(settings, retriever, llm, checkpointer=MemorySaver()), retriever


async def run_graph_answer(graph, q: str, idx: int) -> tuple[str, str, list[str]]:
    """실제 그래프로 답변 생성 → (answer, kb_context, used_tools). kb_context는 실제 인용 청크."""
    final = await graph.ainvoke(
        {"messages": [HumanMessage(content=q)]},
        config={"configurable": {"thread_id": f"eval-{idx}"}, "tags": ["eval"]},
    )
    msgs = final.get("messages", [])
    answer = ""
    for m in reversed(msgs):
        if (
            getattr(m, "content", None)
            and isinstance(m.content, str)
            and not getattr(m, "tool_calls", None)
        ):
            answer = m.content
            break
    cites = final.get("kb_citations", [])
    ctx = "\n".join(c.get("chunk", "")[:400] for c in cites) if cites else ""
    return answer.strip(), ctx, list(final.get("used_tools", []))


async def eval_one(
    graph, retriever, it: dict, sem: asyncio.Semaphore, pool_k: int, do_gen: bool
) -> dict:
    async with sem:
        q = it["question"]
        valid = set(it["valid_sources"])
        gold = it.get("gold_answer", "")
        # ── 검색 지표 ──
        # per_source_cap=99로 raw 풀을 받는다 — 프로덕션 기본 다양화(cap=2)와 무관하게, eval은
        # "초기(크라우딩) → dedup+리랭커(개선)"를 스스로 브래킷팅한다(초기값 안정).
        pool = await retriever.search(
            q, k=pool_k, source_types=MANAGEMENT_SOURCE_TYPES, per_source_cap=99
        )
        base_sources = [c["source"] for c in pool]
        hb, mb = _hit_mrr(base_sources, valid)  # 초기: raw RRF(용어사전 청크가 top 독점)
        # 출처별 중복 제거(문서 단위) — 한 문서의 여러 청크가 top5 칸을 낭비하는 걸 막는다.
        # 프로덕션 search_kb(CRAG)도 (source,title)로 dedup하므로 프로덕션 충실.
        # Hit@5는 문서 단위 지표.
        seen: set = set()
        uniq: list[dict] = []
        for c in pool:
            if c["source"] not in seen:
                seen.add(c["source"])
                uniq.append(c)
        reranked = await rerank(q, uniq)
        hr, mr = _hit_mrr([c["source"] for c in reranked], valid)
        top5 = reranked[:5]
        cp = await context_precision(q, top5)
        rec = {
            "id": it["id"],
            "hit5": [hb, hr],
            "mrr": [round(mb, 3), round(mr, 3)],
            "ctxp": round(cp, 3),
        }
        if not do_gen:
            miss = (
                "" if hr else f"  MISS valid={sorted(valid)} top5={[c['source'] for c in top5][:3]}"
            )
            print(
                f"  [{it['id']:2d}] h {hb}->{hr} m {mb:.2f}->{mr:.2f} cP {cp:.2f}{miss}", flush=True
            )
            return rec
        # ── 생성 지표: 실제 그래프 ──
        ans, ctx, tools = await run_graph_answer(graph, q, it["id"])
        if not ctx:  # 그래프가 search_kb를 안 썼으면 리트리버 컨텍스트로 보정(faith 채점용)
            ctx = "\n".join(c["chunk"][:400] for c in top5)
        before = (await chat(f"질문에 간결히 답하라.\n질문:{q}", 200)).strip()
        faith = await faith_judge(ctx, ans)
        fc_before = await fc_judge(gold, before)
        fc_after = await fc_judge(gold, ans)
        miss = "" if hr else f"  MISS valid={sorted(valid)} top5={[c['source'] for c in top5][:3]}"
        print(
            f"  [{it['id']:2d}] h {hb}->{hr} m {mb:.2f}->{mr:.2f} cP {cp:.2f} "
            f"faith {faith:.1f} FC {fc_before:.1f}->{fc_after:.1f} tools={tools} · {q[:16]}{miss}",
            flush=True,
        )
        rec.update(
            {"faith": faith, "fc": [fc_before, fc_after], "used_tools": tools, "answer": ans[:400]}
        )
        return rec


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=["single", "complex"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--conc", type=int, default=4)
    ap.add_argument("--pool", type=int, default=POOL)
    ap.add_argument("--no-gen", action="store_true", help="검색 지표만(생성 생략) — 빠른 스윕")
    ap.add_argument(
        "--judge",
        choices=["openai", "gemini"],
        default="openai",
        help="채점자 계열 — openai(gpt-4o-mini) | gemini(자기채점 편향 제거, 무료쿼터 회복 시)",
    )
    args = ap.parse_args()
    global JUDGE_PROVIDER
    JUDGE_PROVIDER = args.judge

    data = load_set(args.which)
    if args.limit:
        data = data[: args.limit]
    do_gen = not args.no_gen
    graph, retriever = (
        build_agent_graph()
        if do_gen
        else (None, KbRetriever(embedder=build_embedding_provider(settings)))
    )
    tag = f"{args.which}{'' if do_gen else '_ret'}_pool{args.pool}_{args.judge}"
    out_path = Path(__file__).with_name(f"_golden2_{tag}.jsonl")
    print(
        f"=== 통합 러너 ({args.which}, n={len(data)}, pool={args.pool}, gen={do_gen}, "
        f"judge={args.judge}) ===",
        flush=True,
    )
    sem = asyncio.Semaphore(args.conc)
    results = await asyncio.gather(
        *[eval_one(graph, retriever, it, sem, args.pool, do_gen) for it in data]
    )

    def a(key, idx=None) -> float:
        vals = [(r[key][idx] if idx is not None else r[key]) for r in results if key in r]
        return round(sum(vals) / len(vals), 3) if vals else 0.0

    summary = {
        "which": args.which,
        "n": len(results),
        "pool": args.pool,
        "judge": args.judge,
        "hit5": {"base": a("hit5", 0), "rerank": a("hit5", 1)},
        "mrr": {"base": a("mrr", 0), "rerank": a("mrr", 1)},
        "context_precision": a("ctxp"),
    }
    if do_gen:
        summary["faithfulness"] = a("faith")
        summary["factual_correctness"] = {"before": a("fc", 0), "after": a("fc", 1)}
    with out_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.write(json.dumps({"summary": summary}, ensure_ascii=False) + "\n")
    print("\nSUMMARY " + json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
