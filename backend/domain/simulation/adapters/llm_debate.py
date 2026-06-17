# 실 LLM 토론 엔진 — DebaterPort/JudgePort 구현. 토론자 Haiku/GPT, Judge Sonnet.
#
# 일반인 발화는 실제 반응에, 전문가 발화는 분석 결과(topic)에 grounded — system에 주입.
# 엔진 라우팅: participant.engine(haiku/sonnet→Anthropic, gpt→OpenAI). Gemini는 복구용 잔존(미배정).
# 동기 SDK 호출 — DebateService가 asyncio.to_thread로 감싸 이벤트 루프를 막지 않는다.
from __future__ import annotations

import json
import logging
import os
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from anthropic import Anthropic
    from google.genai import Client as GenaiClient
    from openai import OpenAI

from domain.simulation.contracts.debate_schemas import (
    DebateParticipant,
    DebateTopic,
    JudgeFinal,
    ParticipantDebate,
    RankedAction,
    Stance,
    Utterance,
)
from domain.simulation.contracts.schemas import PersonaReaction

logger = logging.getLogger("clickme")

# 모델 ID — 비용 라인: 토론자 저가(Haiku/mini/Flash), Judge 중상(Sonnet). 바꾸려면 여기만.
HAIKU_MODEL = "claude-haiku-4-5"
SONNET_MODEL = "claude-sonnet-4-6"  # Judge — Opus 4.8에서 다운(호출 적어 비용영향 작음).
OPUS_MODEL = "claude-opus-4-8"  # (미사용·여분) 필요 시 Judge를 다시 올릴 핀.
GPT_MODEL = "gpt-4o-mini"
GEMINI_MODEL = "gemini-2.5-flash"  # (미배정) 복구용 — 응답 실패 잦아 토론자 배정에서 제외

JUDGE_ENGINE = "sonnet"  # LLMJudge 기본 호출 엔진(assigner.JUDGE_ENGINE과 일치).
SUMMARIZE_ENGINE = "haiku"  # 라운드 정리는 한 문장 요약 — 저가 엔진으로(비용 최적화).
_ANTHROPIC_MODELS = {"haiku": HAIKU_MODEL, "sonnet": SONNET_MODEL, "opus": OPUS_MODEL}

_VALID_STANCE = {"positive", "neutral", "negative"}

_PHASE_INSTR = {
    "발산": "다른 참가자를 보지 말고 주제에 독립적으로 반응하라.",
    "반박": "앞선 의견에 동의하거나 반박하라(같은 말 재진술 금지).",
    "검증": "제안된 개선안이 실제로 당신을 움직일지 솔직히 답하라.",
}

_JUDGE_SYS = "당신은 광고 소비자 토론의 주최자입니다. 편향 없이 종합하고 지정 형식으로만 출력하라."


def _strip_json(text: str) -> str:
    """코드펜스(```json …```) 제거 후 JSON 본문만 반환."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t[3:]
        if t[:4].lower() == "json":
            t = t[4:]
        t = t.split("```")[0]
    return t.strip()


def _strip_md(text: str) -> str:
    """마크다운 마커 제거 + 개행→공백 → 한 줄 평문(라운드 정리는 채팅용 한 문장이라 형식 불필요)."""
    t = (text or "").strip()
    t = re.sub(r"-{3,}", " ", t)  # 구분선 ---
    t = re.sub(r"[#*`>|]", "", t)  # 머리글·굵게·코드·인용·표 마커
    t = re.sub(r"\s*\n\s*", " ", t)  # 개행 → 공백
    return re.sub(r"\s{2,}", " ", t).strip()  # 연속 공백 압축


def _norm_stance(value: object) -> Stance:
    s = str(value or "").strip().lower()
    return s if s in _VALID_STANCE else "neutral"  # type: ignore[return-value]


class _Clients:
    """엔진별 SDK 클라이언트 lazy 생성·캐싱 — 필요한 엔진만 초기화."""

    def __init__(self) -> None:
        self._anthropic = None
        self._openai = None
        self._gemini: GenaiClient | None = None
        # 엔진별 누적 토큰(input/output/calls) — complete()가 매 호출 응답의 usage를 더한다.
        # debater·judge가 같은 _Clients를 공유하면 토론 1회 토큰이 여기 모인다(wiring 주입).
        self.usage: dict[str, dict[str, int]] = {}

    def _track(self, engine: str, inp: object, out: object) -> None:
        slot = self.usage.setdefault(engine, {"input": 0, "output": 0, "calls": 0})
        slot["input"] += int(inp or 0)
        slot["output"] += int(out or 0)
        slot["calls"] += 1

    def usage_snapshot(self) -> dict[str, dict[str, int]]:
        """현재까지 누적 토큰의 깊은 복사 — 토론 전후 스냅샷 차이로 1회 사용량을 구한다."""
        return {e: dict(v) for e, v in self.usage.items()}

    def _ant(self) -> Anthropic:
        if self._anthropic is None:
            from anthropic import Anthropic
            from langsmith.wrappers import wrap_anthropic

            # LangSmith 트레이싱(LANGSMITH_TRACING=true일 때만 전송, 아니면 무동작 통과).
            self._anthropic = wrap_anthropic(Anthropic())  # ANTHROPIC_API_KEY
        return self._anthropic

    def _oai(self) -> OpenAI:
        if self._openai is None:
            from langsmith.wrappers import wrap_openai
            from openai import OpenAI

            self._openai = wrap_openai(OpenAI())  # OPENAI_API_KEY
        return self._openai

    def _gem(self) -> GenaiClient:
        if self._gemini is None:
            from google import genai

            self._gemini = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        return self._gemini

    def complete(
        self, engine: str, system: str, user: str, *, json_mode: bool, max_tokens: int = 500
    ) -> str:
        """엔진별 1회 호출 → 원문 텍스트. json_mode면 가능한 SDK는 JSON 응답을 강제."""
        if engine in _ANTHROPIC_MODELS:
            model = _ANTHROPIC_MODELS[engine]
            sys_prompt = system + (" 반드시 JSON만 출력." if json_mode else "")
            r = self._ant().messages.create(
                model=model,
                max_tokens=max_tokens,
                system=sys_prompt,
                messages=[{"role": "user", "content": user}],
            )
            u = getattr(r, "usage", None)
            if u is not None:
                self._track(engine, getattr(u, "input_tokens", 0), getattr(u, "output_tokens", 0))
            return r.content[0].text
        if engine == "gpt":
            kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
            r = self._oai().chat.completions.create(
                model=GPT_MODEL,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                **kwargs,
            )
            u = getattr(r, "usage", None)
            if u is not None:
                self._track(
                    engine, getattr(u, "prompt_tokens", 0), getattr(u, "completion_tokens", 0)
                )
            return r.choices[0].message.content or ""
        if engine == "gemini":
            # 2.5-flash는 thinking 모델 — thinking 토큰이 들쭉날쭉(최대 2000+)해 JSON이 잘린다.
            # 신 SDK(google.genai)로 thinking_budget=0(완전 차단) → 출력만 생성(안정·저렴).
            from google.genai import types

            cfg = types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                response_mime_type="application/json" if json_mode else None,
            )
            r = self._gem().models.generate_content(
                model=GEMINI_MODEL, contents=f"{system}\n\n{user}", config=cfg
            )
            um = getattr(r, "usage_metadata", None)
            if um is not None:
                self._track(
                    engine,
                    getattr(um, "prompt_token_count", 0),
                    getattr(um, "candidates_token_count", 0),
                )
            return r.text
        raise ValueError(f"알 수 없는 엔진: {engine}")

    def complete_json(
        self, engine: str, system: str, user: str, max_tokens: int = 500
    ) -> dict[str, Any]:
        raw = self.complete(engine, system, user, json_mode=True, max_tokens=max_tokens)
        return json.loads(_strip_json(raw))


def _expert_system(p: DebateParticipant, topic: DebateTopic) -> str:
    """전문가 system — 소비자가 아니라 분석 결과를 진단. 수치 밖 사실 금지(분석결과 grounded)."""
    focus = ", ".join(f"{k}={v}" for k, v in (topic.focus or {}).items() if v is not None)
    parts = [
        f"당신은 '{p.persona_name}', {p.persona_profile}입니다.",
        f"토론에서 당신의 역할: {p.role}.",
        "당신은 광고를 본 소비자가 아니라, 아래 시뮬레이션 분석 결과를 진단하는 전문가입니다.",
        f"분석 진단 — {topic.diagnosis}",
    ]
    if focus:
        parts.append(f"근거 수치 — {focus}.")
    parts.append(
        "주어진 분석 수치 밖의 사실을 지어내지 말고, 전문 지식으로 "
        "'왜 이런 결과인지'와 개선 방향을 제시하라."
    )
    return " ".join(parts)


def _persona_system(p: DebateParticipant, r: PersonaReaction | None, topic: DebateTopic) -> str:
    if p.is_expert:
        return _expert_system(p, topic)
    parts = [
        f"당신은 광고를 본 소비자 '{p.persona_name}'({p.persona_profile})입니다.",
        f"토론에서 당신의 역할: {p.role}.",
    ]
    if r is not None:
        acted = "행동(클릭)함" if r.aisas.action else "행동하지 않음"
        rejected = "광고를 거부함" if r.rejected else "거부하지 않음"
        parts.append(
            f"이 광고에 대한 당신의 실제 반응 — 신뢰 {r.trust}/5, 구매의도 {r.purchase_intent}/5, "
            f"{acted}, {rejected}."
        )
        if r.utterance:
            parts.append(f'당신이 광고를 보고 한 말: "{r.utterance}"')
    parts.append("이 캐릭터와 실제 반응에 일관되게 답하라. 새로 지어내지 말 것.")
    return " ".join(parts)


def _round_user(phase: str, topic: DebateTopic) -> str:
    return (
        f"토론 주제: {topic.headline}\n"
        f"이번 라운드({phase}): {_PHASE_INSTR.get(phase, '')}\n"
        "아래 JSON으로만 답하라: "
        '{"stance":"positive|neutral|negative","text":"실제 발언 1~2문장",'
        '"reason":"그렇게 말한 이유","lever":"당신을 움직일 개선점"}'
    )


def _qa_user(question: str, topic: DebateTopic, history: list[Utterance]) -> str:
    """Q&A user 프롬프트 — 주제·사용자 질문·이 참가자의 기존 발언 요약으로 일관된 답변 유도."""
    said = " / ".join(u.text for u in history if u.text)[:600]
    return (
        f"토론 주제: {topic.headline}\n"
        f"당신이 토론에서 한 말 요약: {said or '(없음)'}\n"
        f"사용자 질문: {question}\n"
        "기존 입장과 일관되게 1~2문장으로 답하라. 아래 JSON으로만: "
        '{"stance":"positive|neutral|negative","text":"답변 1~2문장",'
        '"reason":"그렇게 답한 이유","lever":"당신을 움직일 개선점"}'
    )


class LLMDebater:
    """실 LLM 토론자 — participant.engine으로 라우팅, 페르소나 반응에 grounded."""

    def __init__(self, reactions: list[PersonaReaction], clients: _Clients | None = None) -> None:
        self._by_id = {r.persona_id: r for r in reactions}
        self._c = clients or _Clients()

    def speak(
        self, participant: DebateParticipant, round_n: int, phase: str, topic: DebateTopic
    ) -> Utterance:
        r = self._by_id.get(participant.persona_id)
        system, user = _persona_system(participant, r, topic), _round_user(phase, topic)
        # LLM 간헐 실패(빈 응답·파싱)에 대비해 2회 시도. 비결정이라 재시도 시 성공 가능.
        last_exc: Exception | None = None
        for _attempt in range(2):
            try:
                data = self._c.complete_json(participant.engine, system, user, max_tokens=800)
                text = str(data.get("text", "")).strip()
                if not text:
                    raise ValueError("빈 발언")
                return Utterance(
                    round=round_n,
                    phase=phase,
                    stance=_norm_stance(data.get("stance")),
                    text=text[:500],
                    reason=str(data.get("reason", ""))[:300],
                    lever=str(data.get("lever", ""))[:200],
                )
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
        logger.warning(
            "토론자 발화 실패 engine=%s pid=%s err=%s",
            participant.engine,
            participant.persona_id,
            last_exc,
        )
        return Utterance(
            round=round_n,
            phase=phase,
            stance="neutral",
            text="(응답 생성 실패)",
            reason="",
            lever="",
        )

    def answer_question(
        self,
        participant: DebateParticipant,
        question: str,
        topic: DebateTopic,
        history: list[Utterance],
    ) -> Utterance:
        """토론 종료 후 Q&A — 사용자 질문에 대한 답변 1건(phase='질의응답').

        speak()와 동일 패턴 — _persona_system으로 캐릭터 고정, user에 question + history(기존
        발언) 주입해 일관된 답변 생성. JSON 파싱·2회 재시도·실패 시 placeholder Utterance 반환.
        """
        r = self._by_id.get(participant.persona_id)
        system = _persona_system(participant, r, topic)
        user = _qa_user(question, topic, history)
        # LLM 간헐 실패(빈 응답·파싱)에 대비해 2회 시도. 비결정이라 재시도 시 성공 가능.
        last_exc: Exception | None = None
        for _attempt in range(2):
            try:
                data = self._c.complete_json(participant.engine, system, user, max_tokens=800)
                text = str(data.get("text", "")).strip()
                if not text:
                    raise ValueError("빈 답변")
                return Utterance(
                    round=0,
                    phase="질의응답",
                    stance=_norm_stance(data.get("stance")),
                    text=text[:500],
                    reason=str(data.get("reason", ""))[:300],
                    lever=str(data.get("lever", ""))[:200],
                )
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
        logger.warning(
            "Q&A 답변 실패 engine=%s pid=%s err=%s",
            participant.engine,
            participant.persona_id,
            last_exc,
        )
        return Utterance(
            round=0,
            phase="질의응답",
            stance="neutral",
            text="(응답 생성 실패)",
            reason="",
            lever="",
        )


class LLMJudge:
    """실 LLM 주최자 — Sonnet 4.6으로 라운드 정리·잠정 액션·최종 결론(Opus에서 다운)."""

    def __init__(self, clients: _Clients | None = None, engine: str = JUDGE_ENGINE) -> None:
        self._c = clients or _Clients()
        self._engine = engine

    def refine_topic(self, topic: DebateTopic, digest: str) -> DebateTopic:
        """결정론 시드 주제를 데이터 기반 '논쟁적' 주제로 교체(headline/question/diagnosis만)."""
        user = (
            f"광고 반응 분석 요약:\n{digest}\n\n"
            "위 데이터에서 가상 소비자·전문가가 '실제로 의견이 갈릴' 토론 주제 1개를 정하라.\n"
            "- 진단 질문(누구나 답이 같은)이 아니라 대립 가능한 쟁점이어야 한다.\n"
            "- 예: '메시지를 바꿀까 타깃을 바꿀까', '인지가 충분한데 새 메시지가 필요한가'.\n"
            "- 주어진 수치·발언 밖의 사실을 지어내지 말 것.\n"
            '아래 JSON으로만: {"headline":"대립 쟁점 한 문장","question":"핵심 질문",'
            '"diagnosis":"수치 근거 한 줄"}'
        )
        try:
            data = self._c.complete_json(self._engine, _JUDGE_SYS, user, max_tokens=400)
            return topic.model_copy(
                update={
                    "headline": str(data.get("headline") or topic.headline),
                    "question": str(data.get("question") or topic.question),
                    "diagnosis": str(data.get("diagnosis") or topic.diagnosis),
                }
            )
        except Exception:
            logger.exception("Judge 토론 주제 생성 실패(시드 주제 유지)")
            return topic

    def summarize_round(self, round_n: int, utterances: list[Utterance]) -> str:
        body = "\n".join(f"- [{u.stance}] {u.text}" for u in utterances)
        user = (
            f"{round_n}라운드 발언:\n{body}\n\n"
            "핵심 긴장점을 한국어 평문 한 문장으로만 정리하라. "
            "마크다운 금지 — 머리글(#)·굵게(**)·목록·표·구분선·줄바꿈 없이 순수 텍스트 한 문장."
        )
        try:
            # 라운드 정리는 한 문장 요약 — Sonnet 불필요. Haiku로 강등(비용 최적화·품질 무손실).
            raw = self._c.complete(
                SUMMARIZE_ENGINE, _JUDGE_SYS, user, json_mode=False, max_tokens=200
            )
            return _strip_md(raw)  # 모델이 형식을 넣어도 평문 한 줄로 정규화(안전망)
        except Exception:
            logger.exception("Judge 라운드 정리 실패 round=%s", round_n)
            return f"R{round_n}: 정리 실패"

    def finalize(self, topic: DebateTopic, participants: list[ParticipantDebate]) -> JudgeFinal:
        body = self._participants_digest(participants)
        user = (
            f"주제: {topic.headline}\n참가자 발언 요약:\n{body}\n\n"
            "토론 최종 결론을 아래 JSON으로만 출력하라. "
            "headline·consensus·dissent·ranked_actions는 전문가용(정확한 마케팅 용어 허용), "
            "plain_summary는 비전문가용이다 — 마케팅을 전혀 모르는 사람도 한 번에 이해하도록 "
            "전문 용어(퍼널·CTA·전환·포지셔닝 등)를 쓰지 말고, 무엇이 문제인지·왜 그런지·"
            "그래서 무엇을 하면 좋은지를 3~5문장 일상어로 풀어써라.\n"
            "중요: 참가자들이 끝내 합의에 이르지 못했더라도(이견이 남아도) 결론을 미루지 말 것. "
            "headline에는 반드시 '왜 그런지(인과)'를 담고, ranked_actions와 plain_summary에는 "
            "반드시 '다음에 무엇을 할지(구체적 다음 행동)'를 1개 이상 담아라 — "
            "인과와 다음 행동을 한 쌍으로 낸다. "
            "이견이 컸다면 그 이견을 어떻게 검증·해소할지를 다음 행동으로 제시하라. "
            "ranked_actions는 비워두지 말 것(최소 1개).\n"
            '{"headline":"한 문장 진단 — 왜 그런지(인과) 포함(전문가용)",'
            '"plain_summary":"전문 용어 없이 풀어쓴 쉬운 결론 + 다음에 할 행동 3~5문장",'
            '"consensus":["합의점"],"dissent":["이견"],'
            '"ranked_actions":[{"rank":1,"action":"다음에 할 구체적 행동",'
            '"expected_effect":"기대효과","supporting_personas":["이름"]}]}'
        )
        try:
            # final은 진단+합의+이견+개선안(supporting 포함)이라 길다 — 잘리지 않을 만큼만(1200).
            data = self._c.complete_json(self._engine, _JUDGE_SYS, user, max_tokens=1200)
            ranked = [
                RankedAction(
                    rank=int(a.get("rank", i + 1)),
                    action=str(a.get("action", "")),
                    expected_effect=str(a.get("expected_effect", "")),
                    supporting_personas=[str(s) for s in (a.get("supporting_personas") or [])],
                )
                for i, a in enumerate(data.get("ranked_actions") or [])
            ]
            return JudgeFinal(
                headline=str(data.get("headline", topic.diagnosis)),
                plain_summary=str(data.get("plain_summary", "")),
                consensus=[str(s) for s in (data.get("consensus") or [])],
                dissent=[str(s) for s in (data.get("dissent") or [])],
                ranked_actions=ranked,
            )
        except Exception:
            logger.exception("Judge 최종 결론 실패")
            return JudgeFinal(headline=topic.diagnosis)

    @staticmethod
    def _participants_digest(participants: list[ParticipantDebate]) -> str:
        lines = []
        for p in participants:
            last = p.utterances[-1] if p.utterances else None
            stance = last.stance if last else "?"
            text = last.text if last else ""
            lines.append(f"- {p.persona_name}({p.role},{stance}): {text}")
        return "\n".join(lines)
