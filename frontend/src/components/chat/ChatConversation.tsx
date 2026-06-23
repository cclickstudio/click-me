'use client';

// 채팅 대화 본체 — 메시지 렌더 + 입력 + 위젯 + 이미지 첨부 + SSE 전송. /chat 페이지와 플로팅 공용.
// 세션은 props로 제어(sessionId=null이면 새 채팅). 사이드바·프로젝트 게이트는 바깥에서 처리.
import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import SimFormWidget from './SimFormWidget';
import GenFormWidget from './GenFormWidget';
import SimGenListWidget from './SimGenListWidget';
import ApprovalWidget, { type ApprovalSpec } from './ApprovalWidget';
import BatchSimWidget from './BatchSimWidget';
import ReportWidget from './ReportWidget';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// 상대 프록시 URL(/api/...)은 API_BASE를 붙여 렌더. blob:·http:는 그대로 통과.
const fullUrl = (u?: string) => (u && u.startsWith('/') ? `${API_BASE}${u}` : u);

const quickPrompts = [
  '이 광고의 예상 CTR을 분석해줘',
  '20대 여성 타겟 광고 전략을 추천해줘',
  '경쟁사 광고와 비교 분석해줘',
  '광고 카피 개선 방법을 알려줘',
];

type SlashCommand = { cmd: string; label: string; desc: string };
const slashCommands: SlashCommand[] = [
  { cmd: '/시뮬레이션', label: '/시뮬레이션', desc: '광고 시뮬레이션 입력 위젯을 띄웁니다' },
  { cmd: '/제너레이터', label: '/제너레이터', desc: '광고 생성 입력 위젯을 띄웁니다' },
  { cmd: '/비교', label: '/비교', desc: '시뮬레이션 2개의 KPI를 나란히 비교합니다' },
  { cmd: '/도움말', label: '/도움말', desc: '사용 가능한 명령어와 예시를 봅니다' },
  { cmd: '/위젯', label: '/위젯', desc: '사용 가능한 위젯 목록을 봅니다 (개발용)' },
];

type Citation = { kind: string; source: string; title?: string };
type ListItem = {
  id: string;
  title: string;
  status?: string;
  created_at?: string | null;
  sample_size?: number;
  mode?: string;
};
type WidgetSpec = {
  type: string;
  mode?: 'read' | 'select' | 'compare';
  data?: {
    ad_content?: string;
    ad_title?: string;
    product_category?: string;
    ad_objective?: string;
    product_name?: string;
    product_description?: string;
    target_audience?: string;
    campaign_objective?: string;
    items?: ListItem[];
    project_id?: string;
    period?: string;
  };
};
type SourceMeta = {
  source: string;
  label: string;
  engine?: string;
  citations?: Citation[];
  used_tools?: string[];
  widget?: WidgetSpec;
  approval?: ApprovalSpec; // 개선 루프 HITL 수락/거절 카드
};
// 채팅으로 실제 돌린 시뮬/생성 결과 참조 — 내역에 남겨 재로드 시 "결과 보기" 링크로 렌더.
type ResultRef = { kind: 'sim' | 'gen'; id: string };
type Message = {
  role: 'user' | 'assistant';
  content: string;
  meta?: SourceMeta;
  imageUrl?: string;
  imageFile?: File;
  result?: ResultRef;
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

export default function ChatConversation({
  projectId,
  sessionId,
  onSessionCreated,
  onActivity,
}: {
  projectId: string;
  sessionId: string | null; // null = 새 채팅
  onSessionCreated?: (id: string) => void; // 첫 전송으로 세션이 생성되면 알림
  onActivity?: () => void; // 전송 후(제목·갱신 변경) 세션 목록 새로고침 신호
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [slashIndex, setSlashIndex] = useState(0);
  const [attachedImage, setAttachedImage] = useState<File | null>(null);
  const [attachedPreview, setAttachedPreview] = useState<string | null>(null);
  const pendingImageRef = useRef<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const router = useRouter();
  // 이미 로드/생성한 세션 — prop이 같은 값으로 바뀌어도 재로드하지 않게 추적.
  const loadedRef = useRef<string | null | undefined>(undefined);

  const attachImage = (file: File | null) => {
    setAttachedPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return file ? URL.createObjectURL(file) : null;
    });
    setAttachedImage(file);
  };

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming]);

  // sessionId가 바뀌면 그 세션의 DB 내역을 로드(또는 새 채팅이면 비움).
  useEffect(() => {
    if (loadedRef.current === sessionId) return; // 우리가 방금 만든/이미 연 세션 — 재로드 금지
    loadedRef.current = sessionId;
    if (!sessionId) {
      setMessages([]);
      return;
    }
    (async () => {
      try {
        const { messages: rows } = await api.chat.messages(sessionId);
        setMessages(
          rows.map((m) => {
            const rawMeta = m.meta as Record<string, unknown> | null;
            const imageUrl =
              typeof rawMeta?.image_url === 'string' ? rawMeta.image_url : undefined;
            const rr = rawMeta?.result as ResultRef | undefined;
            const result = rr && (rr.kind === 'sim' || rr.kind === 'gen') && rr.id ? rr : undefined;
            // 어시스턴트 메시지만 출처/위젯 meta로 사용. 사용자 메시지 meta는 이미지·결과 참조 보관용.
            const meta = m.role === 'assistant' ? (rawMeta as SourceMeta | null) ?? undefined : undefined;
            return { role: m.role, content: m.content, meta, imageUrl, result };
          }),
        );
      } catch {
        setMessages([]);
      }
    })();
  }, [sessionId]);

  const showSlashMenu = input.startsWith('/') && !input.includes(' ');
  const slashMatches = showSlashMenu ? slashCommands.filter((c) => c.cmd.startsWith(input)) : [];

  const addLocalAssistant = (content: string, meta?: SourceMeta, imageFile?: File) => {
    setMessages((prev) => [...prev, { role: 'assistant', content, meta, imageFile }]);
  };

  const runSlashCommand = (cmd: string) => {
    setInput('');
    setSlashIndex(0);
    const img = attachedImage ?? undefined;
    switch (cmd) {
      case '/시뮬레이션':
        addLocalAssistant(
          '광고 시뮬레이션 입력 위젯입니다. 아래에서 실행하세요.',
          { source: 'simulation', label: '광고 시뮬레이터', widget: { type: 'sim_form' } },
          img,
        );
        attachImage(null);
        break;
      case '/제너레이터':
        addLocalAssistant(
          '광고 생성 입력 위젯입니다. 아래에서 실행하세요.',
          { source: 'generator', label: '광고 생성', widget: { type: 'gen_form' } },
          img,
        );
        attachImage(null);
        break;
      case '/비교':
        // 백엔드로 보내 시뮬 목록(비교 모드) 위젯을 받는다.
        handleSend('/비교');
        break;
      case '/위젯':
        addLocalAssistant(
          [
            '사용 가능한 위젯 목록 (개발/테스트용)',
            '',
            ...slashCommands.filter((c) => c.cmd !== '/위젯').map((c) => `${c.cmd} — ${c.desc}`),
          ].join('\n'),
          { source: 'simulation', label: '위젯 목록' },
        );
        break;
    }
  };

  // SSE 스트림 1건을 소비해 마지막 어시스턴트 메시지에 토큰·meta·approval을 누적.
  // 호출 전 빈 어시스턴트 메시지를 push해둔다(/complete·/approve 공용).
  const consumeStream = useCallback(async (res: Response) => {
    setMessages((prev) => [...prev, { role: 'assistant', content: '' }]);
    const reader = res.body!.getReader();
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
            kind?: string;
            token?: string;
            done?: boolean;
            meta?: SourceMeta;
            approval?: ApprovalSpec;
          };
          // kind 우선 분기, 없으면 레거시 필드(token/meta/done)로 폴백.
          const kind = data.kind ?? (data.done ? 'done' : data.meta ? 'meta' : 'text');
          if (kind === 'done') {
            setIsStreaming(false);
          } else if (kind === 'meta' && data.meta) {
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              const imageFile = data.meta?.widget
                ? pendingImageRef.current ?? undefined
                : last.imageFile;
              return [...prev.slice(0, -1), { ...last, meta: data.meta, imageFile }];
            });
          } else if (kind === 'approval' && data.approval) {
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              const meta = { ...(last.meta ?? { source: 'simulation', label: '개선 제안' }), approval: data.approval };
              return [...prev.slice(0, -1), { ...last, meta }];
            });
          } else if (kind === 'text' && data.token) {
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              return [...prev.slice(0, -1), { ...last, content: last.content + data.token }];
            });
          }
        } catch {
          // ignore malformed SSE line
        }
      }
    }
  }, []);

  // 개선 루프 수락 — POST /api/chat/approve 로 왕복 카운트를 올리고 다음 위젯을 스트리밍.
  const handleApprove = useCallback(
    async (action: string) => {
      if (isStreaming || !sessionId) return;
      setIsStreaming(true);
      try {
        const res = await fetch(`${API_BASE}/api/chat/approve`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action, session_id: sessionId, project_id: projectId }),
        });
        if (!res.ok || !res.body) {
          setIsStreaming(false);
          return;
        }
        await consumeStream(res);
      } catch {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: '진행 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.' },
        ]);
      } finally {
        setIsStreaming(false);
        onActivity?.();
      }
    },
    [isStreaming, sessionId, projectId, consumeStream, onActivity],
  );

  const handleSend = useCallback(
    async (text?: string, resultRef?: ResultRef) => {
      const content = text ?? input.trim();
      if (!content || isStreaming || !projectId) return;

      pendingImageRef.current = attachedImage;
      const imgFile = attachedImage; // S3 영속화용(위젯엔 pendingImageRef로 따로 전달)
      // resultRef: 위젯이 실제 시뮬/생성을 돌린 결과 참조 — 메시지에 남겨 "결과 보기" 링크로.
      const userMsg: Message = {
        role: 'user',
        content,
        imageUrl: attachedPreview ?? undefined,
        result: resultRef,
      };
      const base = messages;
      const newMessages: Message[] = [...base, userMsg];
      setMessages(newMessages);
      setInput('');
      setAttachedImage(null);
      setAttachedPreview(null);
      setIsStreaming(true);

      // 세션이 없으면(새 채팅) 먼저 DB 세션을 만들어 프로젝트에 귀속.
      let sid = sessionId;
      if (!sid) {
        try {
          const created = await api.chat.createSession(projectId);
          sid = created.id;
          loadedRef.current = sid; // prop 변경 시 재로드 방지(현재 대화 유지)
          onSessionCreated?.(sid);
        } catch {
          setMessages((prev) => [
            ...prev,
            { role: 'assistant', content: '채팅 세션을 만들지 못했습니다. 잠시 후 다시 시도해주세요.' },
          ]);
          setIsStreaming(false);
          return;
        }
      }

      // 첨부 이미지를 S3에 1회 업로드 → 사용자 메시지에 영속화(실패해도 표시만 하고 진행).
      let imageUrl: string | undefined;
      if (imgFile) {
        try {
          imageUrl = (await api.chat.uploadImage(imgFile)).url;
        } catch {
          // 업로드 실패 — 이번 세션 표시는 유지되나 내역엔 안 남음
        }
      }

      try {
        const res = await fetch(`${API_BASE}/api/chat/complete`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: sid,
            project_id: projectId,
            messages: newMessages.map((m) => ({ role: m.role, content: m.content })),
            image_url: imageUrl,
            result_ref: resultRef,
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

        await consumeStream(res);
      } catch {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: '서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.' },
        ]);
      } finally {
        setIsStreaming(false);
        pendingImageRef.current = null;
        onActivity?.();
      }
    },
    [input, isStreaming, projectId, attachedImage, attachedPreview, messages, sessionId, onSessionCreated, onActivity, consumeStream],
  );

  return (
    <div className="flex flex-col h-full min-h-0 bg-white dark:bg-[#0F1117] transition-colors">
      {messages.length === 0 ? (
        /* ── Welcome state ── */
        <div className="flex-1 flex flex-col items-center justify-center px-4 pb-10 overflow-y-auto">
          <div className="mb-2 w-10 h-10 flex items-center justify-center rounded-2xl bg-[#EBF3FF] dark:bg-[#1E3A5F]">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#3182F6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
          </div>
          <h2 className="text-lg font-bold text-[#191F28] dark:text-[#F2F4F6] mb-2 mt-3">무엇을 도와드릴까요?</h2>
          <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mb-8 text-center leading-relaxed">
            광고 분석, 성과 예측, 전략 제안까지<br />자유롭게 물어보세요
          </p>
          <div className="grid grid-cols-2 gap-2 w-full max-w-lg">
            {quickPrompts.map((prompt) => (
              <button
                key={prompt}
                onClick={() => handleSend(prompt)}
                className="p-3 text-left text-xs text-[#4E5968] dark:text-[#9CA3AF] bg-[#F9FAFB] dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl hover:border-[#3182F6] hover:text-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-all"
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>
      ) : (
        /* ── Messages ── */
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-2xl mx-auto px-4 py-6 space-y-6">
            {messages.map((msg, i) => {
              if (msg.role === 'assistant' && msg.content === '') return null;
              return (
                <div key={i} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  {msg.role === 'assistant' && (
                    <div className="w-7 h-7 shrink-0 flex items-center justify-center rounded-lg bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6] mt-1">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                      </svg>
                    </div>
                  )}
                  <div className={`flex flex-col gap-1 ${msg.meta?.widget ? 'max-w-md w-full' : 'max-w-sm'} ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                    {msg.role === 'assistant' && msg.meta && (
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                          msg.meta.source === 'management'
                            ? 'bg-[#EBF3FF] text-[#3182F6] dark:bg-[#1E3A5F] dark:text-[#7BB4F5]'
                            : 'bg-[#F2E9FF] text-[#7C3AED] dark:bg-[#2E1F47] dark:text-[#C4A8F5]'
                        }`}
                      >
                        {msg.meta.source === 'management' ? '⚙' : '🧠'} {msg.meta.label}
                      </span>
                    )}
                    {msg.role === 'user' && msg.imageUrl && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={fullUrl(msg.imageUrl)}
                        alt="첨부 이미지"
                        className="max-w-[200px] max-h-[200px] rounded-2xl rounded-br-md object-cover border border-[#E5E8EB] dark:border-[#2D3748]"
                      />
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
                    {msg.result && (
                      <button
                        onClick={() =>
                          router.push(
                            msg.result!.kind === 'sim'
                              ? `/simulation/${msg.result!.id}`
                              : `/generations/${msg.result!.id}`,
                          )
                        }
                        className="self-start mt-0.5 inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[#3182F6]/30 text-[#3182F6] text-xs font-semibold hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-colors"
                      >
                        {msg.result.kind === 'sim' ? '시뮬레이션 결과 보기' : '생성 결과 보기'} →
                      </button>
                    )}
                    {msg.meta?.widget?.type === 'sim_form' && (
                      <SimFormWidget initial={msg.meta.widget.data} initialImage={msg.imageFile} onResult={handleSend} />
                    )}
                    {msg.meta?.widget?.type === 'gen_form' && (
                      <GenFormWidget initial={msg.meta.widget.data} initialImage={msg.imageFile} onResult={handleSend} />
                    )}
                    {msg.meta?.widget?.type === 'sim_list' && (
                      <SimGenListWidget
                        domain="sim"
                        mode={msg.meta.widget.mode ?? 'read'}
                        items={msg.meta.widget.data?.items ?? []}
                        onResult={handleSend}
                      />
                    )}
                    {msg.meta?.widget?.type === 'gen_list' && (
                      <SimGenListWidget
                        domain="gen"
                        mode={msg.meta.widget.mode ?? 'read'}
                        items={msg.meta.widget.data?.items ?? []}
                        onResult={handleSend}
                      />
                    )}
                    {msg.meta?.widget?.type === 'batch_sim_form' && (
                      <BatchSimWidget projectId={projectId} />
                    )}
                    {msg.meta?.widget?.type === 'report_ready' && (
                      <ReportWidget
                        projectId={msg.meta.widget.data?.project_id ?? projectId}
                        period={msg.meta.widget.data?.period}
                      />
                    )}
                    {msg.meta?.approval && (
                      <ApprovalWidget
                        approval={msg.meta.approval}
                        onAccept={handleApprove}
                        disabled={isStreaming}
                      />
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
                  </div>
                </div>
              );
            })}

            {isStreaming &&
              messages.length > 0 &&
              messages[messages.length - 1].role === 'assistant' &&
              messages[messages.length - 1].content === '' && <TypingIndicator />}

            <div ref={bottomRef} />
          </div>
        </div>
      )}

      {/* ── Input bar ── */}
      <div className="border-t border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#1C2333] px-4 py-3 transition-colors shrink-0">
        {attachedPreview && (
          <div className="max-w-2xl mx-auto mb-2 flex items-center gap-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={attachedPreview} alt="첨부 미리보기" className="w-14 h-14 rounded-lg object-cover border border-[#E5E8EB] dark:border-[#2D3748]" />
            <button onClick={() => attachImage(null)} className="text-xs text-[#8B95A1] hover:text-[#F04452]">
              이미지 제거 ✕
            </button>
          </div>
        )}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0] ?? null;
            attachImage(f);
            e.target.value = '';
          }}
        />
        <div className="max-w-2xl mx-auto flex items-end gap-2 relative">
          {slashMatches.length > 0 && (
            <div className="absolute bottom-full left-0 right-0 mb-2 bg-white dark:bg-[#252D3D] border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl shadow-lg overflow-hidden z-10">
              {slashMatches.map((c, i) => {
                const active = i === Math.min(slashIndex, slashMatches.length - 1);
                return (
                  <button
                    key={c.cmd}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      runSlashCommand(c.cmd);
                    }}
                    onMouseEnter={() => setSlashIndex(i)}
                    className={`w-full flex flex-col items-start px-4 py-2.5 text-left transition-colors ${
                      active ? 'bg-[#EBF3FF] dark:bg-[#1E3A5F]' : 'hover:bg-[#F9FAFB] dark:hover:bg-[#1C2333]'
                    }`}
                  >
                    <span className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">{c.label}</span>
                    <span className="text-xs text-[#8B95A1] dark:text-[#6B7280]">{c.desc}</span>
                  </button>
                );
              })}
            </div>
          )}
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isStreaming}
            title="이미지 첨부"
            className="p-3 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] text-[#8B95A1] hover:text-[#3182F6] hover:border-[#3182F6] disabled:opacity-30 transition-all shrink-0"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
            </svg>
          </button>
          <textarea
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              setSlashIndex(0);
            }}
            onKeyDown={(e) => {
              if (slashMatches.length > 0) {
                if (e.key === 'ArrowDown') {
                  e.preventDefault();
                  setSlashIndex((i) => (i + 1) % slashMatches.length);
                  return;
                }
                if (e.key === 'ArrowUp') {
                  e.preventDefault();
                  setSlashIndex((i) => (i - 1 + slashMatches.length) % slashMatches.length);
                  return;
                }
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  runSlashCommand(slashMatches[Math.min(slashIndex, slashMatches.length - 1)].cmd);
                  return;
                }
                if (e.key === 'Escape') {
                  e.preventDefault();
                  setInput('');
                  return;
                }
              }
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="메시지를 입력하세요... (/로 명령어, Shift+Enter로 줄바꿈)"
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
      </div>
    </div>
  );
}
