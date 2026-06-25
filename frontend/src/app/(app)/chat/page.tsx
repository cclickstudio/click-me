'use client';

import { useState, useRef, useEffect } from 'react';
import { safeRandomUUID } from '@/lib/utils';
import { api } from '@/lib/api';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

const quickPrompts = [
  '이 광고의 예상 CTR을 분석해줘',
  '20대 여성 타겟 광고 전략을 추천해줘',
  '경쟁사 광고와 비교 분석해줘',
  '광고 카피 개선 방법을 알려줘',
];

type Citation = {
  kind: string;
  source: string;
  title?: string;
  trust?: string; // system_backed | advisory | reference (KB 근거 신뢰도)
  source_url?: string;
  as_of?: string;
};
type SourceMeta = {
  source: string; // management | clio
  label: string; // 매니지먼트 어시스턴트 | CLIO
  engine: string; // OpenAI · 실측+KB | Gemini
  citations?: Citation[];
  used_tools?: string[];
  thread_id?: string; // 피드백 적재 키
};
type Message = {
  role: 'user' | 'assistant';
  content: string;
  meta?: SourceMeta;
};

function SendIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  );
}

function TypingIndicator() {
  return (
    <div className="flex gap-3 justify-start">
      <div className="w-7 h-7 shrink-0 flex items-center justify-center rounded-lg bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6] mt-1">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
      </div>
      <div className="px-4 py-3 rounded-2xl rounded-bl-md bg-[#F2F4F6] dark:bg-[#252D3D] flex items-center gap-1.5">
        <span className="w-2 h-2 rounded-full bg-[#8B95A1] dark:bg-[#6B7280] animate-bounce [animation-delay:-0.3s]" />
        <span className="w-2 h-2 rounded-full bg-[#8B95A1] dark:bg-[#6B7280] animate-bounce [animation-delay:-0.15s]" />
        <span className="w-2 h-2 rounded-full bg-[#8B95A1] dark:bg-[#6B7280] animate-bounce" />
      </div>
    </div>
  );
}

export default function Page() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [fb, setFb] = useState<Record<number, number>>({}); // 메시지 index → 평가(1/-1)

  // 어시스턴트 답변 평가 적재(좋아요/싫어요) — RAG 품질 개선.
  const sendFeedback = async (i: number, rating: number) => {
    const msg = messages[i];
    setFb((p) => ({ ...p, [i]: rating }));
    try {
      await api.chat.feedback({
        thread_id: msg.meta?.thread_id,
        rating,
        question: messages[i - 1]?.content,
        answer: msg.content,
      });
    } catch {
      /* 적재 실패는 조용히 무시 */
    }
  };
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const sessionId = useRef<string>("");
  if (!sessionId.current) sessionId.current = safeRandomUUID();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming]);

  const handleSend = async (text?: string) => {
    const content = text ?? input.trim();
    if (!content || isStreaming) return;

    const newMessages: Message[] = [...messages, { role: 'user', content }];
    setMessages(newMessages);
    setInput('');
    setIsStreaming(true);

    try {
      const res = await fetch(`${API_BASE}/api/chat/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId.current, messages: newMessages }),
      });

      if (!res.ok || !res.body) {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: '응답을 가져오는 중 오류가 발생했습니다.' },
        ]);
        setIsStreaming(false);
        return;
      }

      // add empty assistant placeholder
      setMessages((prev) => [...prev, { role: 'assistant', content: '' }]);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;
          try {
            const data = JSON.parse(raw) as {
              token?: string;
              done?: boolean;
              meta?: SourceMeta;
            };
            if (data.done) {
              setIsStreaming(false);
            } else if (data.meta) {
              setMessages((prev) => {
                const last = prev[prev.length - 1];
                return [...prev.slice(0, -1), { ...last, meta: data.meta }];
              });
            } else if (data.token) {
              setMessages((prev) => {
                const last = prev[prev.length - 1];
                return [
                  ...prev.slice(0, -1),
                  { ...last, content: last.content + data.token },
                ];
              });
            }
          } catch {
            // ignore malformed SSE line
          }
        }
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: '서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.' },
      ]);
    } finally {
      setIsStreaming(false);
    }
  };

  return (
    <div className="h-screen bg-white dark:bg-[#0F1117] flex flex-col transition-colors">
      <div className="flex-1 flex flex-col overflow-hidden">
        {messages.length === 0 ? (
          /* ── Welcome state ── */
          <div className="flex-1 flex flex-col items-center justify-center px-4 pb-28">
            <div className="mb-2 w-10 h-10 flex items-center justify-center rounded-2xl bg-[#EBF3FF] dark:bg-[#1E3A5F]">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#3182F6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
            </div>
            <h2 className="text-xl font-bold text-[#191F28] dark:text-[#F2F4F6] mb-2 mt-3">무엇을 도와드릴까요?</h2>
            <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mb-10 text-center leading-relaxed">
              광고 분석, 성과 예측, 전략 제안까지<br />자유롭게 물어보세요
            </p>
            <div className="grid grid-cols-2 gap-3 w-full max-w-lg">
              {quickPrompts.map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => handleSend(prompt)}
                  className="p-4 text-left text-sm text-[#4E5968] dark:text-[#9CA3AF] bg-[#F9FAFB] dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl hover:border-[#3182F6] hover:text-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-all"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : (
          /* ── Messages ── */
          <div className="flex-1 overflow-y-auto">
            <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
              {messages.map((msg, i) => {
                // 빈 assistant placeholder는 타이핑 인디케이터로 대체
                if (msg.role === 'assistant' && msg.content === '') return null;
                return (
                  <div
                    key={i}
                    className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    {msg.role === 'assistant' && (
                      <div className="w-7 h-7 shrink-0 flex items-center justify-center rounded-lg bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6] mt-1">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                        </svg>
                      </div>
                    )}
                    <div className={`flex flex-col gap-1 max-w-sm ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                      {msg.role === 'assistant' && msg.meta && (
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                            msg.meta.source === 'management'
                              ? 'bg-[#EBF3FF] text-[#3182F6] dark:bg-[#1E3A5F] dark:text-[#7BB4F5]'
                              : 'bg-[#F2E9FF] text-[#7C3AED] dark:bg-[#2E1F47] dark:text-[#C4A8F5]'
                          }`}
                        >
                          {msg.meta.source === 'management' ? '⚙' : '🧠'} {msg.meta.label} · {msg.meta.engine}
                        </span>
                      )}
                      <div
                        className={`px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
                          msg.role === 'user'
                            ? 'bg-[#3182F6] text-white rounded-br-md'
                            : 'bg-[#F2F4F6] dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6] rounded-bl-md'
                        }`}
                      >
                        {msg.content}
                      </div>
                      {msg.role === 'assistant' &&
                        msg.meta?.source === 'management' &&
                        (msg.meta.citations?.length || msg.meta.used_tools?.length) ? (
                        <div className="flex flex-wrap items-center gap-1 px-1">
                          <span className="text-[10px] text-[#B0B8C1] dark:text-[#6B7280]">근거:</span>
                          {(msg.meta.used_tools ?? []).map((t, ti) => (
                            <span
                              key={`t${ti}`}
                              className="text-[10px] px-1.5 py-0.5 rounded bg-[#EAF2FF] text-[#3182F6] dark:bg-[#1E2A44] dark:text-[#8AB4F8]"
                            >
                              {t
                                .replace('live_campaigns', '실측·캠페인')
                                .replace('live_budget', '실측·예산')
                                .replace('live_campaign_detail', '실측·캠페인')
                                .replace('live_before_after', '실측·전후비교')
                                .replace('search_kb', 'KB')
                                .replace('web_search', '웹')}
                            </span>
                          ))}
                          {(msg.meta.citations ?? [])
                            .filter((c) => c.kind === 'kb')
                            .map((c, ci) => {
                              const trust = c.trust ?? 'system_backed';
                              const style =
                                trust === 'advisory'
                                  ? 'bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
                                  : trust === 'reference'
                                    ? 'bg-[#F2F4F6] text-[#6B7280] dark:bg-[#252D3D] dark:text-[#9CA3AF]'
                                    : 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300';
                              const tag =
                                trust === 'advisory' ? '참고' : trust === 'reference' ? '구성' : '기준';
                              const label =
                                (c.title || c.source.replace('.md', '')) +
                                (c.as_of ? ` · ${c.as_of}` : '') +
                                ` · ${tag}`;
                              const chip = (
                                <span className={`text-[10px] px-1.5 py-0.5 rounded ${style}`}>
                                  {label}
                                </span>
                              );
                              return c.source_url ? (
                                <a
                                  key={`c${ci}`}
                                  href={c.source_url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="hover:underline"
                                  title={c.source_url}
                                >
                                  {chip}
                                </a>
                              ) : (
                                <span key={`c${ci}`}>{chip}</span>
                              );
                            })}
                        </div>
                      ) : null}
                      {/* 매니지먼트 답변 평가(좋아요/싫어요) — RAG 개선 적재 */}
                      {msg.role === 'assistant' && msg.meta?.source === 'management' && msg.content ? (
                        <div className="flex items-center gap-1 px-1">
                          <button
                            onClick={() => sendFeedback(i, 1)}
                            disabled={fb[i] !== undefined}
                            className={`text-[12px] px-1.5 py-0.5 rounded ${
                              fb[i] === 1 ? 'text-[#3182F6]' : 'text-[#B0B8C1] hover:text-[#3182F6]'
                            } disabled:cursor-default`}
                            title="도움이 됐어요"
                          >
                            👍
                          </button>
                          <button
                            onClick={() => sendFeedback(i, -1)}
                            disabled={fb[i] !== undefined}
                            className={`text-[12px] px-1.5 py-0.5 rounded ${
                              fb[i] === -1 ? 'text-red-500' : 'text-[#B0B8C1] hover:text-red-500'
                            } disabled:cursor-default`}
                            title="별로예요"
                          >
                            👎
                          </button>
                          {fb[i] !== undefined && (
                            <span className="text-[10px] text-[#B0B8C1]">평가 감사합니다</span>
                          )}
                        </div>
                      ) : null}
                    </div>
                  </div>
                );
              })}

              {/* 타이핑 인디케이터: 스트리밍 중이고 아직 토큰 미도착 */}
              {isStreaming && messages.length > 0 && messages[messages.length - 1].role === 'assistant' && messages[messages.length - 1].content === '' && (
                <TypingIndicator />
              )}

              <div ref={bottomRef} />
            </div>
          </div>
        )}

        {/* ── Input bar ── */}
        <div className="border-t border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#1C2333] px-4 py-4 transition-colors">
          <div className="max-w-2xl mx-auto flex items-end gap-3">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="메시지를 입력하세요... (Shift+Enter로 줄바꿈)"
              rows={1}
              disabled={isStreaming}
              className="flex-1 px-4 py-3 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] text-sm text-[#191F28] dark:text-[#F2F4F6] placeholder-[#B0B8C1] dark:placeholder-[#4B5563] focus:outline-none focus:border-[#3182F6] focus:ring-2 focus:ring-[#3182F6]/10 transition-colors resize-none overflow-hidden bg-white dark:bg-[#252D3D] leading-relaxed disabled:opacity-60"
              style={{ maxHeight: '120px' }}
            />
            <button
              onClick={() => handleSend()}
              disabled={!input.trim() || isStreaming}
              className="p-3 bg-[#3182F6] text-white rounded-xl hover:bg-[#1B6EEB] disabled:opacity-30 disabled:cursor-not-allowed transition-all shrink-0"
            >
              <SendIcon />
            </button>
          </div>
          <p className="text-center text-xs text-[#B0B8C1] dark:text-[#4B5563] mt-3">
            AI 응답은 참고용이며 실제 광고 성과와 차이가 있을 수 있습니다
          </p>
        </div>
      </div>
    </div>
  );
}
