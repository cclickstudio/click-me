'use client';

import { useState, useRef, useEffect } from 'react';
import { safeRandomUUID } from '@/lib/utils';
import { api } from '@/lib/api';
import { useAuth } from '@/components/AuthProvider';
import { useProjects } from '@/components/ProjectContext';
import { Markdown } from '@/components/Markdown';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

const quickPrompts = [
  '이 광고의 예상 CTR을 분석해줘',
  '20대 여성 타겟 광고 전략을 추천해줘',
  '경쟁사 광고와 비교 분석해줘',
  '광고 카피 개선 방법을 알려줘',
];

type Citation = { kind: string; source: string; title?: string };
type SourceMeta = {
  route?: string; // general | management | simulation | generation
  source: string; // 라우트 값(general | management | ...)
  label: string; // 일반 답변 | 광고 매니지먼트 ...
  engine: string; // direct | management_subagent ...
  citations?: Citation[];
  used_tools?: string[];
  thread_id?: string; // 피드백 적재 키
  requires_approval?: boolean;
};
type StructuredResult = { kind: string; data: unknown };
type ApprovalRequest = {
  tier?: string;
  action_type?: string;
  target_campaign_id?: string | null;
  thread_id?: string;
  rationale?: string;
};
type Message = {
  role: 'user' | 'assistant';
  content: string;
  meta?: SourceMeta;
  results?: StructuredResult[]; // result 프레임 누적(시뮬·생성·집행)
  approval?: ApprovalRequest; // HITL 승인 카드(미결 시 존재)
  approvalResolved?: boolean; // 승인/거부 처리 완료
};

// 오케스트레이터 SSE 프레임 — token/done은 중첩 객체(구버전 평면도 방어적 수용).
type ChatFrame = {
  meta?: SourceMeta;
  token?: string | { text: string };
  result?: StructuredResult;
  tool_status?: { agent?: string; state?: string; label?: string };
  approval_request?: ApprovalRequest;
  done?: boolean | { finish_reason: string };
  error?: { message: string };
};

// result 프레임 kind → 사람이 읽는 라벨(미매핑은 kind 그대로).
const RESULT_LABEL: Record<string, string> = {
  simulation_aggregate: '시뮬레이션 결과',
  execution_result: '집행 결과',
  generation_detail: '생성 결과',
};

function SendIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  );
}

function ImageIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
      <circle cx="8.5" cy="8.5" r="1.5" />
      <polyline points="21 15 16 10 5 21" />
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
  // 로그인 유저의 org + 선택 프로젝트를 챗 요청에 실어 서브에이전트가 테넌트 스코프로 조회.
  const { user } = useAuth();
  const { selectedProjectId } = useProjects();
  const [messages, setMessages] = useState<Message[]>([]);
  const [fb, setFb] = useState<Record<number, number>>({}); // 메시지 index → 평가(1/-1)
  // 첨부 이미지(시뮬 트리거용) — /upload-image 응답 보관 후 다음 전송에 실어 보낸다.
  const [attached, setAttached] = useState<{
    ad_id: string;
    ad_image_url: string | null;
    ad_image_key: string | null;
    preview: string;
    name: string;
  } | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  // 마지막 어시스턴트 메시지에만 변경 적용.
  const applyToLast = (fn: (m: Message) => Message) =>
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (!last || last.role !== 'assistant') return prev;
      return [...prev.slice(0, -1), fn(last)];
    });

  // 오케스트레이터 SSE 프레임 1개를 화면 상태에 반영.
  const handleFrame = (data: ChatFrame) => {
    if (data.meta) {
      applyToLast((m) => ({ ...m, meta: data.meta }));
    } else if (data.token !== undefined) {
      const piece = typeof data.token === 'string' ? data.token : (data.token?.text ?? '');
      applyToLast((m) => ({ ...m, content: m.content + piece }));
    } else if (data.result) {
      applyToLast((m) => ({ ...m, results: [...(m.results ?? []), data.result as StructuredResult] }));
    } else if (data.approval_request) {
      applyToLast((m) => ({ ...m, approval: data.approval_request }));
    } else if (data.error) {
      applyToLast((m) => ({ ...m, content: m.content + `\n⚠ ${data.error?.message ?? '오류'}` }));
    }
    // tool_status·done은 표시 상태에 영향 없음(스트림 종료는 reader가 처리).
  };

  // SSE 본문을 라인 단위로 파싱해 프레임을 반영(complete·resume 공유).
  const readStream = async (res: Response) => {
    if (!res.body) return;
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
          handleFrame(JSON.parse(raw) as ChatFrame);
        } catch {
          // 깨진 SSE 라인 무시
        }
      }
    }
  };

  const handleSend = async (text?: string) => {
    // 이미지만 첨부하고 본문이 비면 시뮬 트리거 기본 문구로(라우팅=시뮬).
    const content = (text ?? input.trim()) || (attached ? '이 광고로 시뮬레이션 돌려줘' : '');
    if (!content || isStreaming) return;

    const sentImage = attached; // 전송 시점 캡처 후 입력 초기화
    const newMessages: Message[] = [...messages, { role: 'user', content }];
    setMessages(newMessages);
    setInput('');
    setAttached(null);
    setIsStreaming(true);

    try {
      const res = await fetch(`${API_BASE}/api/chat/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId.current,
          messages: newMessages,
          organization_id: user?.organization_id ?? null,
          project_id: selectedProjectId ?? null,
          context_ad_id: sentImage?.ad_id ?? null,
          context_ad_image_url: sentImage?.ad_image_url ?? null,
          context_ad_image_key: sentImage?.ad_image_key ?? null,
        }),
      });

      if (!res.ok || !res.body) {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: '응답을 가져오는 중 오류가 발생했습니다.' },
        ]);
        setIsStreaming(false);
        return;
      }

      // 빈 어시스턴트 placeholder 추가 후 스트림 처리(token/meta/result/approval).
      setMessages((prev) => [...prev, { role: 'assistant', content: '' }]);
      await readStream(res);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: '서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.' },
      ]);
    } finally {
      setIsStreaming(false);
    }
  };

  // 이미지 첨부 — /upload-image로 S3 영속화 후 참조 보관(다음 전송에 실어 시뮬 트리거).
  const handleImageSelect = async (file?: File) => {
    if (!file || uploading) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await fetch(`${API_BASE}/api/chat/upload-image`, { method: 'POST', body: form });
      if (!res.ok) throw new Error('upload failed');
      const data = await res.json();
      setAttached({
        ad_id: data.ad_id,
        ad_image_url: data.ad_image_url ?? null,
        ad_image_key: data.ad_image_key ?? null,
        preview: URL.createObjectURL(file),
        name: file.name,
      });
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: '이미지 업로드에 실패했습니다. 다시 시도해주세요.' },
      ]);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  // HITL 승인/거부 → /resume 스트림 재개(같은 어시스턴트 메시지에 이어붙임).
  const handleResume = async (threadId: string, approved: boolean) => {
    if (isStreaming || !threadId) return;
    applyToLast((m) => ({ ...m, approvalResolved: true }));
    setIsStreaming(true);
    try {
      const res = await fetch(`${API_BASE}/api/chat/${threadId}/resume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved, approver_id: 'user' }),
      });
      if (!res.ok || !res.body) {
        applyToLast((m) => ({ ...m, content: m.content + '\n응답을 가져오는 중 오류가 발생했습니다.' }));
        return;
      }
      await readStream(res);
    } catch {
      applyToLast((m) => ({ ...m, content: m.content + '\n서버에 연결할 수 없습니다.' }));
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
                if (
                  msg.role === 'assistant' &&
                  msg.content === '' &&
                  !msg.approval &&
                  !msg.results?.length
                )
                  return null;
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
                      {(msg.role === 'user' || msg.content) && (
                        <div
                          className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${
                            msg.role === 'user'
                              ? 'whitespace-pre-wrap bg-[#3182F6] text-white rounded-br-md'
                              : 'bg-[#F2F4F6] dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6] rounded-bl-md'
                          }`}
                        >
                          {/* 유저=평문, 어시스턴트=마크다운(LLM이 표·볼드 등 md 출력) */}
                          {msg.role === 'user' ? msg.content : <Markdown>{msg.content}</Markdown>}
                        </div>
                      )}
                      {/* 구조화 결과 카드(시뮬·생성·집행) */}
                      {msg.results?.map((r, ri) => (
                        <div
                          key={ri}
                          className="w-full rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-[#F9FAFB] dark:bg-[#1C2333] px-3 py-2"
                        >
                          <p className="text-[10px] font-semibold text-[#8B95A1] dark:text-[#6B7280] mb-1">
                            {RESULT_LABEL[r.kind] ?? r.kind}
                          </p>
                          <pre className="text-[11px] text-[#4E5968] dark:text-[#9CA3AF] whitespace-pre-wrap break-words max-h-48 overflow-y-auto">
                            {JSON.stringify(r.data, null, 2)}
                          </pre>
                        </div>
                      ))}
                      {/* HITL 승인 카드 — 승인/거부 시 /resume 재개 */}
                      {msg.approval && (
                        <div className="w-full rounded-xl border border-[#F2C200] dark:border-[#7A5C00] bg-[#FFF8E1] dark:bg-[#2A2410] px-3 py-3">
                          <p className="text-xs font-semibold text-[#191F28] dark:text-[#F2F4F6]">
                            승인 필요: {msg.approval.action_type}
                            {msg.approval.target_campaign_id ? ` · ${msg.approval.target_campaign_id}` : ''}
                          </p>
                          {msg.approval.rationale && (
                            <p className="text-[11px] text-[#4E5968] dark:text-[#9CA3AF] mt-1">
                              {msg.approval.rationale}
                            </p>
                          )}
                          <div className="flex gap-2 mt-2">
                            <button
                              onClick={() => handleResume(msg.approval?.thread_id ?? '', true)}
                              disabled={msg.approvalResolved || isStreaming}
                              className="px-3 py-1 text-xs font-semibold rounded-lg bg-[#3182F6] text-white hover:bg-[#1B6EEB] disabled:opacity-40 disabled:cursor-not-allowed"
                            >
                              승인
                            </button>
                            <button
                              onClick={() => handleResume(msg.approval?.thread_id ?? '', false)}
                              disabled={msg.approvalResolved || isStreaming}
                              className="px-3 py-1 text-xs font-semibold rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] text-[#4E5968] dark:text-[#9CA3AF] hover:border-red-400 hover:text-red-500 disabled:opacity-40 disabled:cursor-not-allowed"
                            >
                              거부
                            </button>
                          </div>
                          {msg.approvalResolved && (
                            <p className="text-[10px] text-[#B0B8C1] mt-1">처리됨</p>
                          )}
                        </div>
                      )}
                      {msg.role === 'assistant' &&
                        msg.meta?.source === 'management' &&
                        (msg.meta.citations?.length || msg.meta.used_tools?.length) ? (
                        <p className="text-[10px] text-[#B0B8C1] dark:text-[#6B7280] px-1">
                          근거:{' '}
                          {[
                            ...(msg.meta.used_tools ?? []).map((t) => t.replace('live_', '실측·')),
                            ...(msg.meta.citations ?? [])
                              .filter((c) => c.kind === 'kb')
                              .map((c) => c.title || c.source.replace('.md', '')),
                          ].join(' · ')}
                        </p>
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
          <div className="max-w-2xl mx-auto">
            {/* 첨부 이미지 칩 — 다음 전송에 실려 시뮬을 트리거 */}
            {attached && (
              <div className="flex items-center gap-2 mb-2 px-2.5 py-1.5 rounded-lg bg-[#F2F4F6] dark:bg-[#252D3D] w-fit">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={attached.preview} alt="" className="w-8 h-8 rounded object-cover" />
                <span className="text-xs text-[#4E5968] dark:text-[#9CA3AF] max-w-[180px] truncate">
                  {attached.name}
                </span>
                <button
                  onClick={() => setAttached(null)}
                  className="text-[#8B95A1] hover:text-[#191F28] dark:hover:text-white text-sm leading-none"
                  aria-label="첨부 제거"
                >
                  ✕
                </button>
              </div>
            )}
            <div className="flex items-end gap-3">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                hidden
                onChange={(e) => handleImageSelect(e.target.files?.[0])}
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={isStreaming || uploading}
                title="광고 이미지 첨부 — 시뮬레이션 실행"
                className="p-3 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] text-[#4E5968] dark:text-[#9CA3AF] hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] disabled:opacity-40 transition-colors shrink-0"
              >
                {uploading ? <span className="text-xs px-0.5">…</span> : <ImageIcon />}
              </button>
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                placeholder={
                  attached
                    ? '예: 이 광고 시뮬레이션 돌려줘'
                    : '메시지를 입력하세요... (Shift+Enter로 줄바꿈)'
                }
                rows={1}
                disabled={isStreaming}
                className="flex-1 px-4 py-3 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] text-sm text-[#191F28] dark:text-[#F2F4F6] placeholder-[#B0B8C1] dark:placeholder-[#4B5563] focus:outline-none focus:border-[#3182F6] focus:ring-2 focus:ring-[#3182F6]/10 transition-colors resize-none overflow-hidden bg-white dark:bg-[#252D3D] leading-relaxed disabled:opacity-60"
                style={{ maxHeight: '120px' }}
              />
              <button
                onClick={() => handleSend()}
                disabled={(!input.trim() && !attached) || isStreaming}
                className="p-3 bg-[#3182F6] text-white rounded-xl hover:bg-[#1B6EEB] disabled:opacity-30 disabled:cursor-not-allowed transition-all shrink-0"
              >
                <SendIcon />
              </button>
            </div>
          </div>
          <p className="text-center text-xs text-[#B0B8C1] dark:text-[#4B5563] mt-3">
            AI 응답은 참고용이며 실제 광고 성과와 차이가 있을 수 있습니다
          </p>
        </div>
      </div>
    </div>
  );
}
