# 실 LLM 토론 엔진 — DebaterPort/JudgePort 구현. 토론자 Haiku/GPT/Gemini, Judge Opus.
#
# 발화는 실제 반응 데이터(trust·purchase_intent·utterance)에 grounded — system에 주입해 일관 유지.
# 엔진은 participant.engine으로 라우팅(haiku→Anthropic, gpt→OpenAI, gemini→Google).
# 동기 SDK 호출 — DebateService가 asyncio.to_thread로 감싸 이벤트 루프를 막지 않는다.
from __future__ import annotations

import json
import logging
import os
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

# 모델 ID — 비용 라인: 토론자 저가(Haiku/mini/Flash), Judge 강모델(Opus). 바꾸려면 여기만.
HAIKU_MODEL = "claude-haiku-4-5"
OPUS_MODEL = "claude-opus-4-8"
GPT_MODEL = "gpt-4o-mini"
GEMINI_MODEL = "gemini-2.5-flash"  # 기존 어댑터(_common·chat)와 동일 핀

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


def _norm_stance(value: object) -> Stance:
    s = str(value or "").strip().lower()
    return s if s in _VALID_STANCE else "neutral"  # type: ignore[return-value]


class _Clients:
    """엔진별 SDK 클라이언트 lazy 생성·캐싱 — 필요한 엔진만 초기화."""

    def __init__(self) -> None:
        self._anthropic = None
        self._openai = None
        self._gemini: GenaiClient | None = None

    def _ant(self) -> Anthropic:
        if self._anthropic is None:
            from anthropic import Anthropic

            self._anthropic = Anthropic()  # ANTHROPIC_API_KEY
        return self._anthropic

    def _oai(self) -> OpenAI:
        if self._openai is None:
            from openai import OpenAI

            self._openai = OpenAI()  # OPENAI_API_KEY
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
        if engine in ("haiku", "opus"):
            model = OPUS_MODEL if engine == "opus" else HAIKU_MODEL
            sys_prompt = system + (" 반드시 JSON만 출력." if json_mode else "")
            r = self._ant().messages.create(
                model=model,
                max_tokens=max_tokens,
                system=sys_prompt,
                messages=[{"role": "user", "content": user}],
            )
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
            return r.text
        raise ValueError(f"알 수 없는 엔진: {engine}")

    def complete_json(
        self, engine: str, system: str, user: str, max_tokens: int = 500
    ) -> dict[str, Any]:
        raw = self.complete(engine, system, user, json_mode=True, max_tokens=max_tokens)
        return json.loads(_strip_json(raw))


def _persona_system(p: DebateParticipant, r: PersonaReaction | None) -> str:
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


class LLMDebater:
    """실 LLM 토론자 — participant.engine으로 라우팅, 페르소나 반응에 grounded."""

    def __init__(self, reactions: list[PersonaReaction], clients: _Clients | None = None) -> None:
        self._by_id = {r.persona_id: r for r in reactions}
        self._c = clients or _Clients()

    def speak(
        self, participant: DebateParticipant, round_n: int, phase: str, topic: DebateTopic
    ) -> Utterance:
        r = self._by_id.get(participant.persona_id)
        try:
            data = self._c.complete_json(
                participant.engine, _persona_system(participant, r), _round_user(phase, topic)
            )
            return Utterance(
                round=round_n,
                phase=phase,
                stance=_norm_stance(data.get("stance")),
                text=str(data.get("text", ""))[:500],
                reason=str(data.get("reason", ""))[:300],
                lever=str(data.get("lever", ""))[:200],
            )
        except Exception:
            logger.exception(
                "토론자 발화 실패 engine=%s pid=%s", participant.engine, participant.persona_id
            )
            return Utterance(
                round=round_n,
                phase=phase,
                stance="neutral",
                text="(응답 생성 실패)",
                reason="",
                lever="",
            )


class LLMJudge:
    """실 LLM 주최자 — Opus로 라운드 정리·잠정 액션·최종 결론."""

    def __init__(self, clients: _Clients | None = None) -> None:
        self._c = clients or _Clients()

    def summarize_round(self, round_n: int, utterances: list[Utterance]) -> str:
        body = "\n".join(f"- [{u.stance}] {u.text}" for u in utterances)
        user = (
            f"{round_n}라운드 발언:\n{body}\n\n핵심 긴장점을 한 문장으로 정리하라(JSON 아님, 평문)."
        )
        try:
            return self._c.complete(
                "opus", _JUDGE_SYS, user, json_mode=False, max_tokens=200
            ).strip()
        except Exception:
            logger.exception("Judge 라운드 정리 실패 round=%s", round_n)
            return f"R{round_n}: 정리 실패"

    def propose_actions(
        self, topic: DebateTopic, participants: list[ParticipantDebate]
    ) -> list[str]:
        body = self._participants_digest(participants)
        user = (
            f"주제: {topic.headline}\n참가자 발언 요약:\n{body}\n\n"
            '개선 레버 1~3개를 JSON으로: {"actions":["...","..."]}'
        )
        try:
            data = self._c.complete_json("opus", _JUDGE_SYS, user, max_tokens=300)
            return [str(a) for a in (data.get("actions") or [])][:3]
        except Exception:
            logger.exception("Judge 액션 제안 실패")
            return []

    def finalize(self, topic: DebateTopic, participants: list[ParticipantDebate]) -> JudgeFinal:
        body = self._participants_digest(participants)
        user = (
            f"주제: {topic.headline}\n참가자 발언 요약:\n{body}\n\n"
            "토론 최종 결론을 아래 JSON으로만 출력하라:\n"
            '{"headline":"한 문장 진단","consensus":["합의점"],"dissent":["이견"],'
            '"ranked_actions":[{"rank":1,"action":"개선안","expected_effect":"기대효과",'
            '"supporting_personas":["이름"]}]}'
        )
        try:
            data = self._c.complete_json("opus", _JUDGE_SYS, user, max_tokens=700)
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
