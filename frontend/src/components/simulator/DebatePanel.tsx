"use client";
// 시뮬 반응(reactions)을 받아 페르소나 토론(/api/debate/*)을 돌리고 결과를 보여주는 패널.
// 흐름: start(POST) → SSE 스트림(발언 실시간) → completed → result(GET) 결론 표시.
// 발언은 단톡방 채팅처럼 실시간으로 올라온다(진행자=중앙 공지, 참가자=말풍선). 리포트(조각 11) 전 단계.

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type {
  DebateResult,
  DebateSSEEvent,
  DebateStance,
  SimAdAnalysis,
  SimPersona,
  SimPersonaReaction,
} from "@/lib/types";

interface DebatePanelProps {
  reactions: SimPersonaReaction[];
  adAnalysis: SimAdAnalysis | null;
  personas: SimPersona[];
  simulationId?: string;
}

type Phase = "idle" | "running" | "done" | "error";

// 채팅 타임라인 1건 — 참가자 발언 또는 진행자(Judge) 메시지.
type ChatMsg =
  | {
      kind: "utterance";
      round: number;
      phase: string;
      persona_name: string;
      role: string;
      engine: string;
      stance: DebateStance;
      text: string;
      lever: string;
    }
  | { kind: "judge"; variant: "topic" | "round" | "final"; round?: number; text: string };

const STANCE_STYLE: Record<DebateStance, { label: string; dot: string }> = {
  positive: { label: "긍정", dot: "bg-[#00C471]" },
  neutral: { label: "중립", dot: "bg-[#B0B8C1]" },
  negative: { label: "부정", dot: "bg-[#F04452]" },
};

// 역할별 아바타 색 — 한눈에 누가 어떤 진영인지.
const ROLE_AVATAR: Record<string, string> = {
  "도메인 전문가(제품·카테고리)": "bg-[#7C5CFC]",
  "도메인 전문가(시장·유통)": "bg-[#5B8DEF]",
  "마케팅 전문가(퍼포먼스)": "bg-[#00B8B8]",
  "마케팅 전문가(브랜드)": "bg-[#22A06B]",
  피벗: "bg-[#3182F6]",
  완주자: "bg-[#00C471]",
  비판자: "bg-[#F04452]",
  미온: "bg-[#8B95A1]",
};

const STOP_LABEL: Record<string, string> = {
  consensus: "합의 도달",
  dissensus: "이견 잔존",
  max: "최대 라운드",
};

const cardCls =
  "bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6 transition-colors";
const chipBase = "px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors";
const chipActive = "border-[#3182F6] bg-[#EEF4FF] dark:bg-[#1E3A5F] text-[#3182F6]";
const chipIdle =
  "border-[#E5E8EB] dark:border-[#2D3748] text-[#8B95A1] dark:text-[#6B7280] hover:border-[#3182F6]";
const engineBadge =
  "px-1.5 py-0.5 rounded text-[10px] font-mono bg-[#F2F4F6] dark:bg-[#252D3D] text-[#8B95A1] dark:text-[#6B7280]";

function avatarColor(role: string): string {
  return ROLE_AVATAR[role] ?? "bg-[#8B95A1]";
}

export function DebatePanel({ reactions, adAnalysis, personas, simulationId }: DebatePanelProps) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [useLlm, setUseLlm] = useState(false);
  const [layCount, setLayCount] = useState<2 | 4>(4);

  const [stageMsg, setStageMsg] = useState("");
  const [pct, setPct] = useState(0);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [result, setResult] = useState<DebateResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    return () => esRef.current?.close();
  }, []);

  function reset() {
    esRef.current?.close();
    esRef.current = null;
    setMessages([]);
    setResult(null);
    setErrorMsg(null);
    setPct(0);
    setStageMsg("");
  }

  async function startDebate() {
    reset();
    setPhase("running");
    try {
      const { run_id } = await api.debate.start(
        {
          reactions,
          ad_analysis: adAnalysis ?? undefined,
          personas: personas.length > 0 ? personas : undefined,
          simulation_id: simulationId,
        },
        { useLlm, layCount },
      );

      const es = api.debate.stream(run_id);
      esRef.current = es;

      es.onmessage = (ev: MessageEvent) => {
        let data: DebateSSEEvent;
        try {
          data = JSON.parse(ev.data) as DebateSSEEvent;
        } catch {
          return;
        }

        if (data.event === "error") {
          setErrorMsg(data.message ?? "토론 진행 중 오류");
          setPhase("error");
          es.close();
          return;
        }

        if (typeof data.pct === "number") setPct(data.pct);

        if (data.stage === "topic" && data.headline) {
          setMessages((p) => [...p, { kind: "judge", variant: "topic", text: data.headline! }]);
          setStageMsg("토론 주제 제시");
        } else if (data.stage === "utterance" && data.text) {
          const m: ChatMsg = {
            kind: "utterance",
            round: data.round ?? 0,
            phase: data.phase ?? "",
            persona_name: data.persona_name ?? data.persona_id ?? "?",
            role: data.role ?? "",
            engine: data.engine ?? "",
            stance: data.stance ?? "neutral",
            text: data.text,
            lever: data.lever ?? "",
          };
          setMessages((p) => [...p, m]);
          setStageMsg(`R${data.round} ${data.phase} · ${data.persona_name}`);
        } else if (data.stage === "round_summary") {
          setMessages((p) => [
            ...p,
            { kind: "judge", variant: "round", round: data.round, text: data.summary ?? "" },
          ]);
        } else if (data.stage === "judge_final" && data.headline) {
          setMessages((p) => [...p, { kind: "judge", variant: "final", text: data.headline! }]);
          setStageMsg("최종 결론 종합");
        } else if (data.stage) {
          const labels: Record<string, string> = {
            analysis: "반응 분석",
            kpi: "KPI 확정",
            selection: "패널 구성",
            assignment: "엔진·이름 배정",
            report: "리포트 조립",
          };
          if (labels[data.stage]) setStageMsg(labels[data.stage]);
        }

        if (data.event === "completed") {
          es.close();
          esRef.current = null;
          api.debate
            .result(run_id)
            .then((r) => {
              setResult(r);
              setPhase("done");
            })
            .catch((e) => {
              setErrorMsg(e instanceof Error ? e.message : "결과 조회 실패");
              setPhase("error");
            });
        }
      };

      es.onerror = () => {
        if (esRef.current) {
          setErrorMsg("스트림 연결이 끊겼습니다.");
          setPhase("error");
          es.close();
          esRef.current = null;
        }
      };
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : "토론 시작 실패");
      setPhase("error");
    }
  }

  const passedCount = reactions.filter((r) => r.qa_passed).length;

  return (
    <div className={cardCls}>
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">페르소나 토론</h2>
        {phase === "done" && (
          <button
            onClick={startDebate}
            className="text-xs text-[#8B95A1] dark:text-[#6B7280] hover:text-[#3182F6]"
          >
            다시 돌리기
          </button>
        )}
      </div>
      <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mb-4">
        반응 {reactions.length}건(QA 통과 {passedCount})을 전문가 4명 + 일반인 {layCount}명이 토론해
        개선 방향을 도출합니다.
      </p>

      {/* ── 옵션 + 시작 ── */}
      {(phase === "idle" || phase === "error") && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
            <div>
              <p className="text-xs font-semibold text-[#4E5968] dark:text-[#9CA3AF] mb-1.5">
                일반인 수 (lay_count)
              </p>
              <div className="flex gap-2">
                {([2, 4] as const).map((n) => (
                  <button
                    key={n}
                    type="button"
                    onClick={() => setLayCount(n)}
                    className={`${chipBase} ${layCount === n ? chipActive : chipIdle}`}
                  >
                    {n === 2 ? "2명 (피벗·비판자)" : "4명 (+완주자·미온)"}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <p className="text-xs font-semibold text-[#4E5968] dark:text-[#9CA3AF] mb-1.5">
                토론 엔진
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setUseLlm(false)}
                  className={`${chipBase} ${!useLlm ? chipActive : chipIdle}`}
                >
                  Mock (즉시·무료)
                </button>
                <button
                  type="button"
                  onClick={() => setUseLlm(true)}
                  className={`${chipBase} ${useLlm ? chipActive : chipIdle}`}
                >
                  실 LLM (Sonnet·비용)
                </button>
              </div>
            </div>
          </div>

          {errorMsg && (
            <div className="px-4 py-2.5 bg-[#FEF2F2] dark:bg-[#3B0D0D] rounded-xl border border-[#FECACA] dark:border-[#7F1D1D] text-sm text-[#DC2626] dark:text-[#FCA5A5]">
              {errorMsg}
            </div>
          )}

          <button
            onClick={startDebate}
            disabled={reactions.length === 0}
            className="w-full flex items-center justify-center gap-2 py-3 bg-[#3182F6] hover:bg-[#1B6EEB] disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl text-sm font-semibold transition-colors"
          >
            토론 시작
          </button>
          {useLlm && (
            <p className="text-[11px] text-[#B0B8C1] dark:text-[#4B5563] text-center">
              실 LLM은 발언을 또박또박 생성해 30초~1분 이상 걸립니다.
            </p>
          )}
        </div>
      )}

      {/* ── 진행 중 (실시간 채팅) ── */}
      {phase === "running" && (
        <div className="space-y-4">
          <div className="space-y-2">
            <div className="flex justify-between text-xs">
              <span className="text-[#8B95A1] dark:text-[#6B7280] flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-[#3182F6] animate-pulse" />
                {stageMsg || "토론 준비 중..."}
              </span>
              <span className="font-medium text-[#191F28] dark:text-[#F2F4F6]">{pct}%</span>
            </div>
            <div className="w-full bg-[#F2F4F6] dark:bg-[#252D3D] rounded-full h-2 overflow-hidden">
              <div
                className="h-full bg-[#3182F6] rounded-full transition-all duration-300"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
          <ChatView messages={messages} autoScroll typing />
        </div>
      )}

      {/* ── 완료 (결론 + 토론 로그) ── */}
      {phase === "done" && result && <DebateOutcome result={result} messages={messages} />}
    </div>
  );
}

/* ─── 채팅뷰 (단톡방 스타일) — 진행 중·완료 공용 ─── */
function ChatView({
  messages,
  autoScroll = false,
  typing = false,
}: {
  messages: ChatMsg[];
  autoScroll?: boolean;
  typing?: boolean;
}) {
  const boxRef = useRef<HTMLDivElement | null>(null);

  // 새 메시지가 오면 맨 아래로 스크롤(진행 중일 때만).
  useEffect(() => {
    if (autoScroll && boxRef.current) {
      boxRef.current.scrollTop = boxRef.current.scrollHeight;
    }
  }, [messages.length, autoScroll]);

  return (
    <div
      ref={boxRef}
      className="max-h-[460px] overflow-y-auto rounded-xl bg-[#F9FAFB] dark:bg-[#161C29] border border-[#E5E8EB] dark:border-[#2D3748] p-4 space-y-3"
    >
      {messages.length === 0 ? (
        <p className="text-xs text-[#B0B8C1] dark:text-[#4B5563] py-6 text-center">
          곧 진행자가 토론 주제를 제시합니다...
        </p>
      ) : (
        messages.map((m, i) => {
          const prev = messages[i - 1];
          // 라운드가 바뀌는 발언 앞에 구분 칩.
          const showRound =
            m.kind === "utterance" && (prev?.kind !== "utterance" || prev.round !== m.round);
          return (
            <div key={i}>
              {showRound && m.kind === "utterance" && (
                <div className="flex items-center gap-2 my-2">
                  <div className="flex-1 h-px bg-[#E5E8EB] dark:bg-[#2D3748]" />
                  <span className="text-[10px] font-medium text-[#B0B8C1] dark:text-[#4B5563]">
                    라운드 {m.round} · {m.phase}
                  </span>
                  <div className="flex-1 h-px bg-[#E5E8EB] dark:bg-[#2D3748]" />
                </div>
              )}
              <ChatBubble msg={m} />
            </div>
          );
        })
      )}
      {typing && messages.length > 0 && (
        <div className="flex items-center gap-1 pl-1 text-[#B0B8C1] dark:text-[#4B5563]">
          <span className="w-1.5 h-1.5 rounded-full bg-current animate-bounce [animation-delay:-0.2s]" />
          <span className="w-1.5 h-1.5 rounded-full bg-current animate-bounce [animation-delay:-0.1s]" />
          <span className="w-1.5 h-1.5 rounded-full bg-current animate-bounce" />
        </div>
      )}
    </div>
  );
}

/* ─── 채팅 버블 1건 ─── */
function ChatBubble({ msg }: { msg: ChatMsg }) {
  if (msg.kind === "judge") {
    const label =
      msg.variant === "topic" ? "토론 주제" : msg.variant === "final" ? "최종 결론" : `R${msg.round} 정리`;
    return (
      <div className="chat-pop flex justify-center">
        <div className="max-w-[88%] text-center px-3 py-2 rounded-xl bg-[#EEF4FF] dark:bg-[#1E2A44] border border-[#D5E3FB] dark:border-[#26395C]">
          <p className="text-[10px] font-semibold text-[#3182F6] mb-0.5">진행자 · {label}</p>
          <p className="text-xs text-[#4E5968] dark:text-[#C4CCD6] leading-relaxed">{msg.text}</p>
        </div>
      </div>
    );
  }

  const st = STANCE_STYLE[msg.stance];
  const initial = msg.persona_name.charAt(0) || "?";
  return (
    <div className="chat-pop flex gap-2">
      <div
        className={`shrink-0 w-8 h-8 rounded-full ${avatarColor(msg.role)} text-white text-xs font-bold flex items-center justify-center`}
      >
        {initial}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5 mb-0.5">
          <span className="text-[11px] font-medium text-[#191F28] dark:text-[#F2F4F6]">
            {msg.persona_name}
          </span>
          <span className="text-[10px] text-[#8B95A1] dark:text-[#6B7280]">{msg.role}</span>
          <span className={engineBadge}>{msg.engine}</span>
          <span className="flex items-center gap-1 text-[10px] text-[#8B95A1] dark:text-[#6B7280]">
            <span className={`w-1.5 h-1.5 rounded-full ${st.dot}`} />
            {st.label}
          </span>
        </div>
        <div className="inline-block px-3 py-2 rounded-2xl rounded-tl-sm bg-white dark:bg-[#252D3D] border border-[#E5E8EB] dark:border-[#2D3748]">
          <p className="text-sm text-[#191F28] dark:text-[#F2F4F6] leading-relaxed">{msg.text}</p>
        </div>
        {msg.lever && (
          <p className="text-[11px] text-[#B0B8C1] dark:text-[#4B5563] mt-0.5 pl-1">
            개선 레버: {msg.lever}
          </p>
        )}
      </div>
    </div>
  );
}

/* ─── 토론 결론 화면 ─── */
function DebateOutcome({ result, messages }: { result: DebateResult; messages: ChatMsg[] }) {
  const rep = result.report;
  const debate = result.debate;
  const roundSummaries = debate?.round_summaries ?? {};

  return (
    <div className="space-y-5">
      {/* 메타 배지 */}
      <div className="flex flex-wrap gap-2 text-xs">
        <span className="px-2.5 py-1 rounded-full bg-[#EEF4FF] dark:bg-[#1E3A5F] text-[#3182F6]">
          {rep.rounds_run}라운드
        </span>
        {rep.stop_reason && (
          <span className="px-2.5 py-1 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] text-[#4E5968] dark:text-[#9CA3AF]">
            {STOP_LABEL[rep.stop_reason] ?? rep.stop_reason}
          </span>
        )}
        {debate?.models.judge && (
          <span className="px-2.5 py-1 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] text-[#4E5968] dark:text-[#9CA3AF]">
            Judge {debate.models.judge}
          </span>
        )}
        {debate?.models.engines && (
          <span className="px-2.5 py-1 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] text-[#4E5968] dark:text-[#9CA3AF]">
            토론자 {debate.models.engines.join("·")}
          </span>
        )}
      </div>

      {/* 비전문가용 쉬운 결론 (강조) */}
      {rep.plain_summary && (
        <div className="rounded-xl bg-[#EEF4FF] dark:bg-[#162844] border border-[#D5E3FB] dark:border-[#1E3A5F] p-4">
          <p className="text-xs font-semibold text-[#3182F6] mb-1.5">한눈에 보는 결론</p>
          <p className="text-[15px] leading-relaxed text-[#191F28] dark:text-[#F2F4F6]">
            {rep.plain_summary}
          </p>
        </div>
      )}

      {/* 전문가용 진단 헤드라인 */}
      <div>
        <p className="text-xs font-semibold text-[#8B95A1] dark:text-[#6B7280] mb-1">진단 (전문가용)</p>
        <p className="text-sm text-[#191F28] dark:text-[#F2F4F6] leading-relaxed">{rep.headline}</p>
      </div>

      {/* 합의 / 이견 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {rep.consensus.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-[#00A661] mb-1.5">합의점</p>
            <ul className="space-y-1">
              {rep.consensus.map((c, i) => (
                <li key={i} className="text-sm text-[#4E5968] dark:text-[#9CA3AF] flex gap-1.5">
                  <span className="text-[#00A661]">•</span>
                  <span>{c}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {rep.dissent.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-[#F4A100] mb-1.5">이견</p>
            <ul className="space-y-1">
              {rep.dissent.map((d, i) => (
                <li key={i} className="text-sm text-[#4E5968] dark:text-[#9CA3AF] flex gap-1.5">
                  <span className="text-[#F4A100]">•</span>
                  <span>{d}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* 개선안 순위 */}
      {rep.ranked_actions.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-[#8B95A1] dark:text-[#6B7280] mb-2">개선안 (우선순위)</p>
          <div className="space-y-2">
            {rep.ranked_actions.map((a) => (
              <div
                key={a.rank}
                className="flex gap-3 p-3 rounded-xl bg-[#F9FAFB] dark:bg-[#252D3D] border border-[#E5E8EB] dark:border-[#2D3748]"
              >
                <span className="shrink-0 w-6 h-6 rounded-full bg-[#3182F6] text-white text-xs font-bold flex items-center justify-center">
                  {a.rank}
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-[#191F28] dark:text-[#F2F4F6]">{a.action}</p>
                  {a.expected_effect && (
                    <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mt-0.5">
                      기대효과: {a.expected_effect}
                    </p>
                  )}
                  {a.supporting_personas.length > 0 && (
                    <p className="text-[11px] text-[#B0B8C1] dark:text-[#4B5563] mt-0.5">
                      뒷받침: {a.supporting_personas.join(", ")}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 라운드 정리 (있으면) */}
      {Object.keys(roundSummaries).length > 0 && (
        <div>
          <p className="text-xs font-semibold text-[#8B95A1] dark:text-[#6B7280] mb-1.5">라운드 정리</p>
          <ul className="space-y-1">
            {Object.entries(roundSummaries).map(([round, summary]) => (
              <li key={round} className="text-xs text-[#4E5968] dark:text-[#9CA3AF]">
                <span className="font-medium">R{round}</span> · {summary}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 토론 전체 로그(채팅) */}
      <div>
        <p className="text-xs font-semibold text-[#8B95A1] dark:text-[#6B7280] mb-2">토론 전체 로그</p>
        <ChatView messages={messages} />
      </div>

      {!rep.debate_available && (
        <p className="text-xs text-[#F4A100]">
          토론 미실행 상태의 리포트입니다(KPI·분석만). 토론 엔진을 확인하세요.
        </p>
      )}
    </div>
  );
}
