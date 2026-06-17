"use client";
// 토론 종료 후 Q&A 채팅 — 사용자가 질문하면 /api/debate/{run_id}/question(POST SSE)으로
// 페르소나가 한 명씩 답한다. DM 스타일 3열: 페르소나=왼쪽, 주최자=가운데, 내 질문=오른쪽.

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { DebateStance, QAEvent, SimAdAnalysis, SimPersonaReaction } from "@/lib/types";
import { STANCE_STYLE, avatarColor, engineBadge } from "./DebatePanel";

interface DebateQAPanelProps {
  runId: string;
  reactions: SimPersonaReaction[];
  adAnalysis: SimAdAnalysis | null;
}

// Q&A 타임라인 1건 — 내 질문(오른쪽) / 주최자(가운데) / 페르소나 답변(왼쪽).
type QAMsg =
  | { kind: "question"; text: string }
  | { kind: "moderator"; text: string }
  | {
      kind: "answer";
      persona_name: string;
      role: string;
      engine: string;
      stance: DebateStance;
      text: string;
      reason: string;
      lever: string;
    };

export function DebateQAPanel({ runId, reactions, adAnalysis }: DebateQAPanelProps) {
  const [messages, setMessages] = useState<QAMsg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const boxRef = useRef<HTMLDivElement | null>(null);

  // 새 메시지가 오면 맨 아래로 스크롤.
  useEffect(() => {
    if (boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight;
  }, [messages.length]);

  async function ask() {
    const question = input.trim();
    if (!question || busy) return;

    setErrorMsg(null);
    setBusy(true);
    setInput("");
    setMessages((p) => [...p, { kind: "question", text: question }]);

    try {
      await api.debate.question(
        runId,
        { question, reactions, ad_analysis: adAnalysis ?? undefined },
        (ev: QAEvent) => {
          if (ev.event === "error") {
            setErrorMsg(ev.message ?? "Q&A 진행 중 오류");
            return;
          }
          if (ev.event === "completed") return;
          if (ev.stage === "qa_moderator") {
            setMessages((p) => [...p, { kind: "moderator", text: ev.text }]);
          } else if (ev.stage === "qa_utterance") {
            setMessages((p) => [
              ...p,
              {
                kind: "answer",
                persona_name: ev.persona_name || ev.persona_id || "?",
                role: ev.role ?? "",
                engine: ev.engine ?? "",
                stance: ev.stance ?? "neutral",
                text: ev.text ?? "",
                reason: ev.reason ?? "",
                lever: ev.lever ?? "",
              },
            ]);
          }
        },
      );
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : "질문 전송 실패");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-6 pt-5 border-t border-[#E5E8EB] dark:border-[#2D3748]">
      <h3 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-1">토론 Q&amp;A</h3>
      <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mb-4">
        토론에 참여한 페르소나에게 추가로 질문해보세요. 한 명씩 답합니다.
      </p>

      {/* 채팅 영역 */}
      <div
        ref={boxRef}
        className="max-h-[420px] overflow-y-auto rounded-xl bg-[#F9FAFB] dark:bg-[#161C29] border border-[#E5E8EB] dark:border-[#2D3748] p-4 space-y-3"
      >
        {messages.length === 0 ? (
          <p className="text-xs text-[#B0B8C1] dark:text-[#4B5563] py-6 text-center">
            아래 입력창에 질문을 적어 토론을 이어가세요.
          </p>
        ) : (
          messages.map((m, i) => <QABubble key={i} msg={m} />)
        )}
        {busy && (
          <div className="flex items-center gap-1 pl-1 text-[#B0B8C1] dark:text-[#4B5563]">
            <span className="w-1.5 h-1.5 rounded-full bg-current animate-bounce [animation-delay:-0.2s]" />
            <span className="w-1.5 h-1.5 rounded-full bg-current animate-bounce [animation-delay:-0.1s]" />
            <span className="w-1.5 h-1.5 rounded-full bg-current animate-bounce" />
          </div>
        )}
      </div>

      {errorMsg && (
        <div className="mt-3 px-4 py-2.5 bg-[#FEF2F2] dark:bg-[#3B0D0D] rounded-xl border border-[#FECACA] dark:border-[#7F1D1D] text-sm text-[#DC2626] dark:text-[#FCA5A5]">
          {errorMsg}
        </div>
      )}

      {/* 입력창 */}
      <div className="mt-3 flex items-end gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              ask();
            }
          }}
          rows={1}
          placeholder="페르소나에게 질문하기 (Enter 전송 · Shift+Enter 줄바꿈)"
          disabled={busy}
          className="flex-1 px-4 py-2.5 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#252D3D] text-sm text-[#191F28] dark:text-[#F2F4F6] focus:outline-none focus:ring-2 focus:ring-[#3182F6] placeholder:text-[#B0B8C1] dark:placeholder:text-[#4B5563] transition-colors resize-none disabled:opacity-50"
        />
        <button
          onClick={ask}
          disabled={busy || !input.trim()}
          className="shrink-0 px-5 py-2.5 bg-[#3182F6] hover:bg-[#1B6EEB] disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl text-sm font-semibold transition-colors"
        >
          전송
        </button>
      </div>
    </div>
  );
}

/* ─── Q&A 버블 1건 (3열 정렬) ─── */
function QABubble({ msg }: { msg: QAMsg }) {
  // 내 질문 — 오른쪽.
  if (msg.kind === "question") {
    return (
      <div className="chat-pop flex justify-end">
        <div className="max-w-[80%] inline-block px-3 py-2 rounded-2xl rounded-tr-sm bg-[#3182F6] text-white">
          <p className="text-sm leading-relaxed">{msg.text}</p>
        </div>
      </div>
    );
  }

  // 주최자 — 가운데.
  if (msg.kind === "moderator") {
    return (
      <div className="chat-pop flex justify-center">
        <div className="max-w-[88%] text-center px-3 py-2 rounded-xl bg-[#EEF4FF] dark:bg-[#1E2A44] border border-[#D5E3FB] dark:border-[#26395C]">
          <p className="text-[10px] font-semibold text-[#3182F6] mb-0.5">주최자</p>
          <p className="text-xs text-[#4E5968] dark:text-[#C4CCD6] leading-relaxed">{msg.text}</p>
        </div>
      </div>
    );
  }

  // 페르소나 답변 — 왼쪽 (DebatePanel ChatBubble 톤 재사용).
  const st = STANCE_STYLE[msg.stance];
  const initial = msg.persona_name.charAt(0) || "?";
  return (
    <div className="chat-pop flex gap-2 justify-start">
      <div
        className={`shrink-0 w-8 h-8 rounded-full ${avatarColor(msg.role)} text-white text-xs font-bold flex items-center justify-center`}
      >
        {initial}
      </div>
      <div className="min-w-0 max-w-[80%]">
        <div className="flex flex-wrap items-center gap-1.5 mb-0.5">
          <span className="text-[11px] font-medium text-[#191F28] dark:text-[#F2F4F6]">
            {msg.persona_name}
          </span>
          {msg.role && (
            <span className="text-[10px] text-[#8B95A1] dark:text-[#6B7280]">{msg.role}</span>
          )}
          {msg.engine && <span className={engineBadge}>{msg.engine}</span>}
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
