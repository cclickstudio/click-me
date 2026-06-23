'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import AppLayout from '@/components/AppLayout';
import { useProjects } from '@/components/ProjectContext';
import { api, type ChatSessionRow } from '@/lib/api';
import SimFormWidget from '@/components/chat/SimFormWidget';
import GenFormWidget from '@/components/chat/GenFormWidget';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

const quickPrompts = [
  '이 광고의 예상 CTR을 분석해줘',
  '20대 여성 타겟 광고 전략을 추천해줘',
  '경쟁사 광고와 비교 분석해줘',
  '광고 카피 개선 방법을 알려줘',
];

// 입력창 "/" 자동완성으로 띄우는 슬래시 커맨드 목록
type SlashCommand = {
  cmd: string; // 매칭/표시용 (예: '/시뮬레이션')
  label: string;
  desc: string;
};
const slashCommands: SlashCommand[] = [
  { cmd: '/시뮬레이션', label: '/시뮬레이션', desc: '광고 시뮬레이션 입력 위젯을 띄웁니다' },
  { cmd: '/제너레이터', label: '/제너레이터', desc: '광고 생성 입력 위젯을 띄웁니다' },
  { cmd: '/위젯', label: '/위젯', desc: '사용 가능한 위젯 목록을 봅니다 (개발용)' },
];

type Citation = { kind: string; source: string; title?: string };
type WidgetSpec = {
  type: string;
  data?: {
    ad_content?: string;
    ad_title?: string;
    product_category?: string;
    ad_objective?: string;
    product_name?: string;
    product_description?: string;
    target_audience?: string;
    campaign_objective?: string;
  };
};
type SourceMeta = {
  source: string; // management | clio | simulation | generator
  label: string;
  engine?: string;
  citations?: Citation[];
  used_tools?: string[];
  widget?: WidgetSpec; // 기능 실행 위젯(sim_form 등)
};
type Message = {
  role: 'user' | 'assistant';
  content: string;
  meta?: SourceMeta;
  imageUrl?: string; // 사용자 메시지에 첨부된 이미지 미리보기(object URL)
  imageFile?: File; // 위젯으로 넘길 첨부 이미지 원본(클라이언트 전용, DB 미저장)
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
  const { projects, selectedProject, selectProject } = useProjects();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [slashIndex, setSlashIndex] = useState(0); // 드롭다운 하이라이트 위치
  const [sessions, setSessions] = useState<ChatSessionRow[]>([]); // 프로젝트별 채팅 목록
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null); // DB 세션 id
  const [attachedImage, setAttachedImage] = useState<File | null>(null); // 입력바 첨부 이미지
  const [attachedPreview, setAttachedPreview] = useState<string | null>(null);
  const pendingImageRef = useRef<File | null>(null); // 이번 턴 위젯으로 넘길 이미지
  const fileInputRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // 이미지 첨부/해제 — object URL은 교체·해제 시 revoke.
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

  // 프로젝트별 세션 목록 로드(최근 갱신 순).
  const loadSessions = useCallback(async (projectId: string) => {
    try {
      const { sessions: rows } = await api.chat.sessions(projectId);
      setSessions(rows);
    } catch {
      setSessions([]);
    }
  }, []);

  // 프로젝트가 바뀌면 그 프로젝트의 채팅 목록을 다시 불러오고 현재 대화를 비운다.
  useEffect(() => {
    if (!selectedProject) {
      setSessions([]);
      setMessages([]);
      setCurrentSessionId(null);
      return;
    }
    setMessages([]);
    setCurrentSessionId(null);
    loadSessions(selectedProject.id);
  }, [selectedProject, loadSessions]);

  // "/"로 시작하고 공백이 없을 때만 자동완성 후보를 노출
  const showSlashMenu = input.startsWith('/') && !input.includes(' ');
  const slashMatches = showSlashMenu
    ? slashCommands.filter((c) => c.cmd.startsWith(input))
    : [];

  // 로컬 assistant 메시지 추가 (백엔드 호출 없이 위젯/안내 띄우기)
  const addLocalAssistant = (content: string, meta?: SourceMeta, imageFile?: File) => {
    setMessages((prev) => [...prev, { role: 'assistant', content, meta, imageFile }]);
  };

  const runSlashCommand = (cmd: string) => {
    setInput('');
    setSlashIndex(0);
    const img = attachedImage ?? undefined; // 첨부 이미지가 있으면 위젯으로 전달
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
      case '/위젯':
        addLocalAssistant(
          [
            '사용 가능한 위젯 목록 (개발/테스트용)',
            '',
            ...slashCommands
              .filter((c) => c.cmd !== '/위젯')
              .map((c) => `${c.cmd} — ${c.desc}`),
          ].join('\n'),
          { source: 'simulation', label: '위젯 목록' },
        );
        break;
    }
  };

  // 새 채팅 — 현재 대화·세션을 비운다(첫 전송 시 세션 생성).
  const newChat = () => {
    setMessages([]);
    setCurrentSessionId(null);
    setInput('');
  };

  // 기존 세션 열기 — DB 내역을 불러와 메시지로 복원.
  const openSession = async (sessionId: string) => {
    if (isStreaming) return;
    try {
      const { messages: rows } = await api.chat.messages(sessionId);
      setMessages(
        rows.map((m) => ({
          role: m.role,
          content: m.content,
          meta: (m.meta as SourceMeta | null) ?? undefined,
        })),
      );
      setCurrentSessionId(sessionId);
    } catch {
      // ignore — 내역 로드 실패 시 현재 상태 유지
    }
  };

  const deleteSession = async (sessionId: string) => {
    try {
      await api.chat.deleteSession(sessionId);
    } catch {
      // ignore
    }
    if (currentSessionId === sessionId) newChat();
    if (selectedProject) loadSessions(selectedProject.id);
  };

  const handleSend = async (text?: string) => {
    const content = text ?? input.trim();
    if (!content || isStreaming || !selectedProject) return;

    // 첨부 이미지를 이번 턴 사용자 메시지에 싣고, 결과 위젯으로 넘길 수 있게 보관.
    pendingImageRef.current = attachedImage;
    const userMsg: Message = { role: 'user', content, imageUrl: attachedPreview ?? undefined };
    const newMessages: Message[] = [...messages, userMsg];
    setMessages(newMessages);
    setInput('');
    setAttachedImage(null);
    setAttachedPreview(null);
    setIsStreaming(true);

    // 세션이 없으면(새 채팅) 먼저 DB 세션을 만들어 프로젝트에 귀속.
    let sid = currentSessionId;
    if (!sid) {
      try {
        const created = await api.chat.createSession(selectedProject.id);
        sid = created.id;
        setCurrentSessionId(sid);
      } catch {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: '채팅 세션을 만들지 못했습니다. 잠시 후 다시 시도해주세요.' },
        ]);
        setIsStreaming(false);
        return;
      }
    }

    try {
      const res = await fetch(`${API_BASE}/api/chat/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sid,
          messages: newMessages.map((m) => ({ role: m.role, content: m.content })),
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
                // 위젯이 오면 이번 턴 첨부 이미지를 그 위젯 메시지에 실어준다.
                const imageFile = data.meta?.widget
                  ? pendingImageRef.current ?? undefined
                  : last.imageFile;
                return [...prev.slice(0, -1), { ...last, meta: data.meta, imageFile }];
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
      pendingImageRef.current = null; // 위젯에 전달됐거나 미사용 — 어느 쪽이든 해제
      // 제목·갱신 시각이 바뀌었을 수 있으니 목록 갱신.
      if (selectedProject) loadSessions(selectedProject.id);
    }
  };

  // ── 프로젝트 미선택 — 채팅 시작 전 프로젝트를 먼저 고르게 한다 ──
  if (!selectedProject) {
    return (
      <AppLayout>
        <div className="h-screen flex flex-col items-center justify-center px-4 bg-white dark:bg-[#0F1117] transition-colors">
          <div className="mb-3 w-12 h-12 flex items-center justify-center rounded-2xl bg-[#EBF3FF] dark:bg-[#1E3A5F]">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#3182F6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
          </div>
          <h2 className="text-xl font-bold text-[#191F28] dark:text-[#F2F4F6] mb-2">먼저 프로젝트를 선택하세요</h2>
          <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mb-8 text-center leading-relaxed">
            채팅은 프로젝트에 저장됩니다.<br />프로젝트를 고르면 그 프로젝트의 채팅 목록이 열립니다.
          </p>
          {projects.length === 0 ? (
            <p className="text-sm text-[#B0B8C1]">사용 가능한 프로젝트가 없습니다. 먼저 프로젝트를 생성하세요.</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-lg">
              {projects.map((p) => (
                <button
                  key={p.id}
                  onClick={() => selectProject(p.id)}
                  className="p-4 text-left bg-[#F9FAFB] dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl hover:border-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-all"
                >
                  <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">{p.name}</p>
                  {p.organization_name && (
                    <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mt-0.5">{p.organization_name}</p>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="h-screen bg-white dark:bg-[#0F1117] flex transition-colors">
        {/* ── 세션 사이드바 — 프로젝트별 채팅 목록 ── */}
        <aside className="w-64 shrink-0 border-r border-[#E5E8EB] dark:border-[#2D3748] flex flex-col bg-[#F9FAFB] dark:bg-[#141925]">
          <div className="px-4 py-4 border-b border-[#E5E8EB] dark:border-[#2D3748]">
            <p className="text-[11px] font-semibold text-[#8B95A1] dark:text-[#6B7280] uppercase tracking-wide">프로젝트</p>
            <div className="flex items-center justify-between gap-2 mt-1">
              <p className="text-sm font-bold text-[#191F28] dark:text-[#F2F4F6] truncate">{selectedProject.name}</p>
              <button
                onClick={() => selectProject(null)}
                className="text-[11px] text-[#8B95A1] hover:text-[#3182F6] shrink-0"
                title="다른 프로젝트 선택"
              >
                변경
              </button>
            </div>
          </div>
          <button
            onClick={newChat}
            className="mx-3 mt-3 mb-1 py-2 rounded-lg bg-[#3182F6] text-white text-sm font-semibold hover:bg-[#1B6EEB] transition-colors"
          >
            + 새 채팅
          </button>
          <div className="flex-1 overflow-y-auto px-2 py-2 space-y-1">
            {sessions.length === 0 ? (
              <p className="px-2 py-3 text-xs text-[#B0B8C1] dark:text-[#4B5563]">아직 채팅이 없어요.</p>
            ) : (
              sessions.map((s) => {
                const active = s.id === currentSessionId;
                return (
                  <div
                    key={s.id}
                    className={`group flex items-center gap-1 rounded-lg px-2 py-2 cursor-pointer transition-colors ${
                      active
                        ? 'bg-[#EBF3FF] dark:bg-[#1E3A5F]'
                        : 'hover:bg-white dark:hover:bg-[#1C2333]'
                    }`}
                    onClick={() => openSession(s.id)}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-[#191F28] dark:text-[#F2F4F6] truncate">{s.title}</p>
                      <p className="text-[10px] text-[#B0B8C1] dark:text-[#6B7280]">{s.message_count}개 메시지</p>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteSession(s.id);
                      }}
                      className="opacity-0 group-hover:opacity-100 text-[#B0B8C1] hover:text-[#F04452] text-xs shrink-0 px-1"
                      title="삭제"
                    >
                      ✕
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </aside>

        {/* ── 채팅 영역 ── */}
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
                          {msg.meta.engine ? ` · ${msg.meta.engine}` : ''}
                        </span>
                      )}
                      {msg.role === 'user' && msg.imageUrl && (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={msg.imageUrl}
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
                      {msg.meta?.widget?.type === 'sim_form' && (
                        <SimFormWidget initial={msg.meta.widget.data} initialImage={msg.imageFile} onResult={handleSend} />
                      )}
                      {msg.meta?.widget?.type === 'gen_form' && (
                        <GenFormWidget initial={msg.meta.widget.data} initialImage={msg.imageFile} onResult={handleSend} />
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
          {/* 첨부 이미지 미리보기 */}
          {attachedPreview && (
            <div className="max-w-2xl mx-auto mb-2 flex items-center gap-2">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={attachedPreview} alt="첨부 미리보기" className="w-14 h-14 rounded-lg object-cover border border-[#E5E8EB] dark:border-[#2D3748]" />
              <button
                onClick={() => attachImage(null)}
                className="text-xs text-[#8B95A1] hover:text-[#F04452]"
              >
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
              e.target.value = ''; // 같은 파일 재선택 허용
            }}
          />
          <div className="max-w-2xl mx-auto flex items-end gap-3 relative">
            {/* 슬래시 커맨드 자동완성 드롭다운 */}
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
                        active
                          ? 'bg-[#EBF3FF] dark:bg-[#1E3A5F]'
                          : 'hover:bg-[#F9FAFB] dark:hover:bg-[#1C2333]'
                      }`}
                    >
                      <span className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">
                        {c.label}
                      </span>
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
                // 슬래시 메뉴가 열려 있으면 방향키/Enter로 항목 선택
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
          <p className="text-center text-xs text-[#B0B8C1] dark:text-[#4B5563] mt-3">
            AI 응답은 참고용이며 실제 광고 성과와 차이가 있을 수 있습니다
          </p>
        </div>
        </div>
      </div>
    </AppLayout>
  );
}
