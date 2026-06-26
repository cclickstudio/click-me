'use client';

import { useState, useRef, useEffect } from 'react';
import { safeRandomUUID } from '@/lib/utils';
import { api } from '@/lib/api';
import { getToken } from '@/lib/authApi';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

const quickPrompts = [
  '이 광고의 예상 CTR을 분석해줘',
  '20대 여성 타겟 광고 전략을 추천해줘',
  '경쟁사 광고와 비교 분석해줘',
  '광고 카피 개선 방법을 알려줘',
];

// ── 타입 ──────────────────────────────────────────────────────────────────────

type Citation = { kind: string; source: string; title?: string };
type SourceMeta = {
  source: string;
  label: string;
  engine: string;
  citations?: Citation[];
  used_tools?: string[];
  thread_id?: string;
  needs_assets?: boolean;
};
type StartedEvent = {
  event: string;
  job_id: string;
  stream_url: string;
  domain: string;
};
type Message = {
  role: 'user' | 'assistant';
  content: string;
  meta?: SourceMeta;
};

// ── 아이콘 ────────────────────────────────────────────────────────────────────

function SendIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  );
}

function ChatIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}

// ── 서브 컴포넌트 ─────────────────────────────────────────────────────────────

function TypingIndicator() {
  return (
    <div className="flex gap-3 justify-start">
      <div className="w-7 h-7 shrink-0 flex items-center justify-center rounded-lg bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6] mt-1">
        <ChatIcon />
      </div>
      <div className="px-4 py-3 rounded-2xl rounded-bl-md bg-[#F2F4F6] dark:bg-[#252D3D] flex items-center gap-1.5">
        <span className="w-2 h-2 rounded-full bg-[#8B95A1] dark:bg-[#6B7280] animate-bounce [animation-delay:-0.3s]" />
        <span className="w-2 h-2 rounded-full bg-[#8B95A1] dark:bg-[#6B7280] animate-bounce [animation-delay:-0.15s]" />
        <span className="w-2 h-2 rounded-full bg-[#8B95A1] dark:bg-[#6B7280] animate-bounce" />
      </div>
    </div>
  );
}

function ProgressCard({ pct, message }: { pct: number; message: string }) {
  return (
    <div className="bg-[#EBF3FF] dark:bg-[#1E3A5F] rounded-2xl rounded-bl-md px-4 py-3 max-w-sm">
      <p className="text-xs font-medium text-[#3182F6] mb-2">광고 생성 중...</p>
      <div className="w-full bg-[#CDDEF9] dark:bg-[#2D4A7A] rounded-full h-1.5 mb-2">
        <div
          className="bg-[#3182F6] h-1.5 rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-[#4E5968] dark:text-[#9CA3AF]">{message}</p>
    </div>
  );
}

function AssetUploadCard({
  sessionId,
  brandLogoPreview,
  productImagePreview,
  uploadingLogo,
  uploadingProduct,
  onLogoChange,
  onProductChange,
  onConfirm,
  onSkip,
}: {
  sessionId: string;
  brandLogoPreview: string | null;
  productImagePreview: string | null;
  uploadingLogo: boolean;
  uploadingProduct: boolean;
  onLogoChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onProductChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onConfirm: () => void;
  onSkip: () => void;
}) {
  return (
    <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-4 max-w-sm">
      <div className="flex gap-3 mb-4">
        {/* 브랜드 로고 */}
        <div className="flex-1">
          <p className="text-[11px] text-[#8B95A1] dark:text-[#6B7280] mb-1.5">
            브랜드 로고 <span className="text-[#E53E3E]">*</span>
          </p>
          <label className="block cursor-pointer">
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              className="hidden"
              disabled={!sessionId || uploadingLogo}
              onChange={onLogoChange}
            />
            {brandLogoPreview ? (
              <div className="relative">
                <img src={brandLogoPreview} alt="브랜드 로고" className="w-full h-16 object-contain border border-[#E5E8EB] dark:border-[#2D3748] rounded-lg bg-[#F9FAFB] dark:bg-[#252D3D]" />
                <span className="absolute top-1 right-1 text-[10px] text-[#3182F6] bg-white dark:bg-[#1C2333] px-1.5 py-0.5 rounded">변경</span>
              </div>
            ) : (
              <div className={`flex flex-col items-center justify-center h-16 border-2 border-dashed border-[#E5E8EB] dark:border-[#2D3748] rounded-lg hover:border-[#3182F6] transition-colors ${uploadingLogo ? 'opacity-60' : ''}`}>
                {uploadingLogo ? (
                  <p className="text-xs text-[#8B95A1]">업로드 중...</p>
                ) : (
                  <>
                    <p className="text-xs text-[#8B95A1] dark:text-[#6B7280]">클릭하여 업로드</p>
                    <p className="text-[10px] text-[#B0B8C1] dark:text-[#4B5563]">PNG · JPG · WebP</p>
                  </>
                )}
              </div>
            )}
          </label>
        </div>

        {/* 상품 이미지 */}
        <div className="flex-1">
          <p className="text-[11px] text-[#8B95A1] dark:text-[#6B7280] mb-1.5">
            상품 이미지 <span className="text-[#B0B8C1] dark:text-[#4B5563]">(선택)</span>
          </p>
          <label className="block cursor-pointer">
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              className="hidden"
              disabled={uploadingProduct}
              onChange={onProductChange}
            />
            {productImagePreview ? (
              <div className="relative">
                <img src={productImagePreview} alt="상품 이미지" className="w-full h-16 object-contain border border-[#E5E8EB] dark:border-[#2D3748] rounded-lg bg-[#F9FAFB] dark:bg-[#252D3D]" />
                <span className="absolute top-1 right-1 text-[10px] text-[#3182F6] bg-white dark:bg-[#1C2333] px-1.5 py-0.5 rounded">변경</span>
              </div>
            ) : (
              <div className={`flex flex-col items-center justify-center h-16 border-2 border-dashed border-[#E5E8EB] dark:border-[#2D3748] rounded-lg hover:border-[#3182F6] transition-colors ${uploadingProduct ? 'opacity-60' : ''}`}>
                {uploadingProduct ? (
                  <p className="text-xs text-[#8B95A1]">업로드 중...</p>
                ) : (
                  <>
                    <p className="text-xs text-[#8B95A1] dark:text-[#6B7280]">클릭하여 업로드</p>
                    <p className="text-[10px] text-[#B0B8C1] dark:text-[#4B5563]">PNG · JPG · WebP</p>
                  </>
                )}
              </div>
            )}
          </label>
        </div>
      </div>

      <div className="flex gap-2">
        <button
          onClick={onConfirm}
          disabled={!brandLogoPreview || uploadingLogo || uploadingProduct}
          className="flex-1 py-2 text-xs font-semibold text-white bg-[#3182F6] rounded-lg hover:bg-[#1B6EEB] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          생성 시작
        </button>
        <button
          onClick={onSkip}
          disabled={uploadingLogo || uploadingProduct}
          className="flex-1 py-2 text-xs font-medium text-[#4E5968] dark:text-[#9CA3AF] border border-[#E5E8EB] dark:border-[#2D3748] rounded-lg hover:border-[#3182F6] hover:text-[#3182F6] transition-colors"
        >
          이미지 없이 진행
        </button>
      </div>
    </div>
  );
}

// ── 메인 ──────────────────────────────────────────────────────────────────────

export default function Page() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [fb, setFb] = useState<Record<number, number>>({});
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);

  // 이미지 업로드
  const [brandLogoKey, setBrandLogoKey] = useState<string | null>(null);
  const [brandLogoPreview, setBrandLogoPreview] = useState<string | null>(null);
  const [productImageKey, setProductImageKey] = useState<string | null>(null);
  const [productImagePreview, setProductImagePreview] = useState<string | null>(null);
  const [uploadingLogo, setUploadingLogo] = useState(false);
  const [uploadingProduct, setUploadingProduct] = useState(false);

  // 이미지 건너뛰기 — 세션 내 유지(한 번 건너뛰면 다음 요청에서도 재요청 안 함)
  const [skipAssets, setSkipAssets] = useState(false);

  // 생성 진행
  const [progress, setProgress] = useState<{ pct: number; message: string } | null>(null);
  const [generationId, setGenerationId] = useState<string | null>(null);

  const sessionId = useRef<string>('');
  if (!sessionId.current) sessionId.current = safeRandomUUID();
  const esRef = useRef<EventSource | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming, progress]);

  useEffect(() => () => { esRef.current?.close(); }, []);

  // 어시스턴트 답변 평가 적재
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
    } catch { /* 적재 실패는 조용히 무시 */ }
  };

  // 생성 잡 SSE 구독 — TRIGGER 후 stream_url로 진행률 수신
  function subscribeGenerationSSE(streamUrl: string, jobId: string) {
    esRef.current?.close();
    const es = new EventSource(`${API_BASE}${streamUrl}`);
    esRef.current = es;
    setGenerationId(jobId);

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.event === 'progress') {
          setProgress({ pct: data.pct ?? 0, message: data.message ?? '' });
        } else if (data.event === 'completed') {
          setProgress(null);
          es.close();
          setMessages((prev) => [
            ...prev,
            { role: 'assistant', content: '광고 생성이 완료됐어요. 결과를 확인해보세요.' },
          ]);
        } else if (data.event === 'error') {
          setProgress(null);
          es.close();
          setMessages((prev) => [
            ...prev,
            { role: 'assistant', content: `생성 중 오류가 발생했어요: ${data.message ?? ''}` },
          ]);
        }
      } catch { /* malformed SSE 무시 */ }
    };
    es.onerror = () => { setProgress(null); es.close(); };
  }

  async function handleLogoChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingLogo(true);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch(`${API_BASE}/api/generator/logo`, {
        method: 'POST',
        headers: { 'x-client-id': sessionId.current },
        body: formData,
      });
      if (!res.ok) return;
      const data = await res.json();
      setBrandLogoKey(data.key);
      setBrandLogoPreview(`${API_BASE}${data.url}`);
    } finally {
      setUploadingLogo(false);
      e.target.value = '';
    }
  }

  async function handleProductChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingProduct(true);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch(`${API_BASE}/api/generator/product-image`, {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) return;
      const data = await res.json();
      setProductImageKey(data.temp_key);
      setProductImagePreview(URL.createObjectURL(file));
    } finally {
      setUploadingProduct(false);
      e.target.value = '';
    }
  }

  const handleSend = async (text?: string, opts?: { skipOverride?: boolean }) => {
    const content = text ?? input.trim();
    if (!content || isStreaming || !!progress) return;
    const effectiveSkip = opts?.skipOverride ?? skipAssets;

    const newMessages: Message[] = [...messages, { role: 'user', content }];
    setMessages(newMessages);
    setInput('');
    setIsStreaming(true);

    const token = getToken();
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    try {
      const res = await fetch(`${API_BASE}/api/chat/complete`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          session_id: sessionId.current,
          messages: newMessages,
          product_image_temp_key: productImageKey ?? undefined,
          brand_logo_s3_key: brandLogoKey ?? undefined,
          skip_asset_prompt: effectiveSkip,
        }),
      });

      if (!res.ok || !res.body) {
        setMessages((prev) => [...prev, { role: 'assistant', content: '응답을 가져오는 중 오류가 발생했습니다.' }]);
        setIsStreaming(false);
        return;
      }

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
              started?: StartedEvent;
            };
            if (data.done) {
              setIsStreaming(false);
            } else if (data.started) {
              // TRIGGER — 생성 잡 시작, stream_url 구독
              subscribeGenerationSSE(data.started.stream_url, data.started.job_id);
            } else if (data.meta) {
              setMessages((prev) => {
                const last = prev[prev.length - 1];
                return [...prev.slice(0, -1), { ...last, meta: data.meta }];
              });
            } else if (data.token) {
              setMessages((prev) => {
                const last = prev[prev.length - 1];
                return [...prev.slice(0, -1), { ...last, content: last.content + data.token }];
              });
            }
          } catch { /* malformed SSE 무시 */ }
        }
      }
    } catch {
      setMessages((prev) => [...prev, { role: 'assistant', content: '서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.' }]);
    } finally {
      setIsStreaming(false);
    }
  };

  return (
    <div className="h-screen bg-white dark:bg-[#0F1117] flex transition-colors overflow-hidden">

      {/* ── 채팅 영역 ── */}
      <div className="flex-1 flex flex-col min-w-0">
        {messages.length === 0 ? (
          /* Welcome */
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
          /* Messages */
          <div className="flex-1 overflow-y-auto">
            <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
              {messages.map((msg, i) => {
                if (msg.role === 'assistant' && msg.content === '') return null;
                return (
                  <div key={i} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    {msg.role === 'assistant' && (
                      <div className="w-7 h-7 shrink-0 flex items-center justify-center rounded-lg bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6] mt-1">
                        <ChatIcon />
                      </div>
                    )}
                    <div className={`flex flex-col gap-1 max-w-sm ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                      {msg.role === 'assistant' && msg.meta && (
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                          msg.meta.source === 'management'
                            ? 'bg-[#EBF3FF] text-[#3182F6] dark:bg-[#1E3A5F] dark:text-[#7BB4F5]'
                            : msg.meta.source === 'generator'
                            ? 'bg-[#EDFCF2] text-[#12B76A] dark:bg-[#1A3A2A] dark:text-[#6EE7B7]'
                            : 'bg-[#F2E9FF] text-[#7C3AED] dark:bg-[#2E1F47] dark:text-[#C4A8F5]'
                        }`}>
                          {msg.meta.source === 'management' ? '⚙' : msg.meta.source === 'generator' ? '✦' : '🧠'}{' '}
                          {msg.meta.label} · {msg.meta.engine}
                        </span>
                      )}
                      <div className={`px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
                        msg.role === 'user'
                          ? 'bg-[#3182F6] text-white rounded-br-md'
                          : 'bg-[#F2F4F6] dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6] rounded-bl-md'
                      }`}>
                        {msg.content}
                      </div>
                      {msg.role === 'assistant' && msg.meta?.source === 'management' &&
                        (msg.meta.citations?.length || msg.meta.used_tools?.length) ? (
                        <p className="text-[10px] text-[#B0B8C1] dark:text-[#6B7280] px-1">
                          근거:{' '}
                          {[
                            ...(msg.meta.used_tools ?? []).map((t) => t.replace('live_', '실측·')),
                            ...(msg.meta.citations ?? []).filter((c) => c.kind === 'kb').map((c) => c.title || c.source.replace('.md', '')),
                          ].join(' · ')}
                        </p>
                      ) : null}
                      {msg.role === 'assistant' && msg.meta?.source === 'management' && msg.content ? (
                        <div className="flex items-center gap-1 px-1">
                          <button onClick={() => sendFeedback(i, 1)} disabled={fb[i] !== undefined}
                            className={`text-[12px] px-1.5 py-0.5 rounded ${fb[i] === 1 ? 'text-[#3182F6]' : 'text-[#B0B8C1] hover:text-[#3182F6]'} disabled:cursor-default`}
                            title="도움이 됐어요">👍</button>
                          <button onClick={() => sendFeedback(i, -1)} disabled={fb[i] !== undefined}
                            className={`text-[12px] px-1.5 py-0.5 rounded ${fb[i] === -1 ? 'text-red-500' : 'text-[#B0B8C1] hover:text-red-500'} disabled:cursor-default`}
                            title="별로예요">👎</button>
                          {fb[i] !== undefined && <span className="text-[10px] text-[#B0B8C1]">평가 감사합니다</span>}
                        </div>
                      ) : null}
                    </div>
                  </div>
                );
              })}

              {/* 인라인 에셋 업로드 카드 — 마지막 어시스턴트 메시지가 needs_assets일 때만 표시 */}
              {(() => {
                const last = messages[messages.length - 1];
                if (!isStreaming && !progress && last?.role === 'assistant' && last?.meta?.needs_assets) {
                  return (
                    <div className="flex gap-3 justify-start pl-10">
                      <AssetUploadCard
                        sessionId={sessionId.current}
                        brandLogoPreview={brandLogoPreview}
                        productImagePreview={productImagePreview}
                        uploadingLogo={uploadingLogo}
                        uploadingProduct={uploadingProduct}
                        onLogoChange={handleLogoChange}
                        onProductChange={handleProductChange}
                        onConfirm={() => handleSend('이미지를 업로드했어요. 생성을 시작해주세요.')}
                        onSkip={() => {
                          setSkipAssets(true);
                          handleSend('이미지 없이 진행해주세요.', { skipOverride: true });
                        }}
                      />
                    </div>
                  );
                }
                return null;
              })()}

              {/* 생성 진행률 */}
              {progress && (
                <div className="flex gap-3 justify-start">
                  <div className="w-7 h-7 shrink-0 flex items-center justify-center rounded-lg bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6] mt-1">
                    <ChatIcon />
                  </div>
                  <ProgressCard pct={progress.pct} message={progress.message} />
                </div>
              )}

              {/* 생성 완료 — 결과 이동 버튼 */}
              {!progress && generationId && (
                <div className="flex justify-start pl-10">
                  <a
                    href={`/generations/${generationId}`}
                    className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-[#3182F6] rounded-xl hover:bg-[#1B6EEB] transition-colors"
                  >
                    결과 보기
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M5 12h14M12 5l7 7-7 7" />
                    </svg>
                  </a>
                </div>
              )}

              {isStreaming && messages.length > 0 && messages[messages.length - 1].role === 'assistant' && messages[messages.length - 1].content === '' && (
                <TypingIndicator />
              )}

              <div ref={bottomRef} />
            </div>
          </div>
        )}

        {/* 입력창 */}
        <div className="border-t border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#1C2333] px-4 py-4 transition-colors">
          <div className="max-w-2xl mx-auto flex items-end gap-3">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
              }}
              placeholder="메시지를 입력하세요... (Shift+Enter로 줄바꿈)"
              rows={1}
              disabled={isStreaming || !!progress}
              className="flex-1 px-4 py-3 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] text-sm text-[#191F28] dark:text-[#F2F4F6] placeholder-[#B0B8C1] dark:placeholder-[#4B5563] focus:outline-none focus:border-[#3182F6] focus:ring-2 focus:ring-[#3182F6]/10 transition-colors resize-none overflow-hidden bg-white dark:bg-[#252D3D] leading-relaxed disabled:opacity-60"
              style={{ maxHeight: '120px' }}
            />
            <button
              onClick={() => handleSend()}
              disabled={!input.trim() || isStreaming || !!progress}
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
