"use client";

import { useEffect, useRef, useState } from "react";
import AppLayout from "@/components/AppLayout";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SESSION_KEY = "generator_chat_session_id";

// ── 타입 ──────────────────────────────────────────────────────────────────────

type Role = "user" | "assistant";

interface ChatMessage {
  role: Role;
  content: string;
}

interface PartialRequest {
  product_name?: string;
  product_description?: string;
  target_audience?: string;
  tone_and_manner?: string;
  campaign_objective?: string;
  brand_color?: string;
  brand_logo_s3_key?: string;
  product_image_temp_key?: string;
}

interface SendResult {
  response: string;
  partial_request: PartialRequest;
  status: string;
  generation_id: string | null;
}

interface SSEEvent {
  event: string;
  stage?: string;
  pct?: number;
  message?: string;
}

// ── 아이콘 ────────────────────────────────────────────────────────────────────

function SendIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  );
}

function SparkleIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 17l-6.2 4.3 2.4-7.4L2 9.4h7.6z" />
    </svg>
  );
}

// ── 서브 컴포넌트 ─────────────────────────────────────────────────────────────

function TypingIndicator() {
  return (
    <div className="flex gap-3 justify-start">
      <div className="w-7 h-7 shrink-0 flex items-center justify-center rounded-lg bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6] mt-1">
        <SparkleIcon />
      </div>
      <div className="px-4 py-3 rounded-2xl rounded-bl-md bg-[#F2F4F6] dark:bg-[#252D3D] flex items-center gap-1.5">
        <span className="w-2 h-2 rounded-full bg-[#8B95A1] dark:bg-[#6B7280] animate-bounce [animation-delay:-0.3s]" />
        <span className="w-2 h-2 rounded-full bg-[#8B95A1] dark:bg-[#6B7280] animate-bounce [animation-delay:-0.15s]" />
        <span className="w-2 h-2 rounded-full bg-[#8B95A1] dark:bg-[#6B7280] animate-bounce" />
      </div>
    </div>
  );
}

function InfoCard({ partial }: { partial: PartialRequest }) {
  const LABELS: Record<string, string> = {
    product_name: "상품명",
    product_description: "상품 설명",
    target_audience: "타겟층",
    tone_and_manner: "톤앤매너",
    campaign_objective: "캠페인 목표",
  };
  const REQUIRED = ["product_name", "product_description", "target_audience"];
  const entries = Object.entries(LABELS);
  const filled = REQUIRED.filter((k) => !!(partial as Record<string, string>)[k]).length;

  return (
    <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-4">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs font-semibold text-[#4E5968] dark:text-[#9CA3AF]">수집된 정보</p>
        <span className="text-xs text-[#3182F6] font-medium">{filled}/3 필수</span>
      </div>
      <div className="space-y-2">
        {entries.map(([key, label]) => {
          const value = (partial as Record<string, string>)[key];
          const isRequired = REQUIRED.includes(key);
          return (
            <div key={key} className="flex gap-2 items-start">
              <span
                className={`mt-0.5 w-1.5 h-1.5 rounded-full shrink-0 ${
                  value ? "bg-[#3182F6]" : isRequired ? "bg-[#E5E8EB] dark:bg-[#2D3748]" : "bg-[#E5E8EB] dark:bg-[#2D3748]"
                }`}
              />
              <div className="min-w-0">
                <p className="text-[11px] text-[#8B95A1] dark:text-[#6B7280]">{label}{isRequired ? " *" : ""}</p>
                {value ? (
                  <p className="text-xs text-[#191F28] dark:text-[#F2F4F6] truncate">{value}</p>
                ) : (
                  <p className="text-xs text-[#B0B8C1] dark:text-[#4B5563]">미수집</p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function UploadPanel({
  sessionId,
  brandLogoPreview,
  productImagePreview,
  uploadingLogo,
  uploadingProduct,
  onLogoChange,
  onProductChange,
}: {
  sessionId: string | null;
  brandLogoPreview: string | null;
  productImagePreview: string | null;
  uploadingLogo: boolean;
  uploadingProduct: boolean;
  onLogoChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onProductChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
}) {
  return (
    <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-4">
      <p className="text-xs font-semibold text-[#4E5968] dark:text-[#9CA3AF] mb-3">에셋 업로드</p>

      {/* 브랜드 로고 */}
      <div className="mb-3">
        <p className="text-[11px] text-[#8B95A1] dark:text-[#6B7280] mb-1.5">브랜드 로고</p>
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
              <img
                src={brandLogoPreview}
                alt="브랜드 로고"
                className="w-full h-16 object-contain border border-[#E5E8EB] dark:border-[#2D3748] rounded-lg bg-[#F9FAFB] dark:bg-[#252D3D]"
              />
              <span className="absolute top-1 right-1 text-[10px] text-[#3182F6] bg-white dark:bg-[#1C2333] px-1.5 py-0.5 rounded">
                변경
              </span>
            </div>
          ) : (
            <div
              className={`flex flex-col items-center justify-center h-16 border-2 border-dashed border-[#E5E8EB] dark:border-[#2D3748] rounded-lg hover:border-[#3182F6] transition-colors ${uploadingLogo ? "opacity-60" : ""}`}
            >
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
      <div>
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
              <img
                src={productImagePreview}
                alt="상품 이미지"
                className="w-full h-16 object-contain border border-[#E5E8EB] dark:border-[#2D3748] rounded-lg bg-[#F9FAFB] dark:bg-[#252D3D]"
              />
              <span className="absolute top-1 right-1 text-[10px] text-[#3182F6] bg-white dark:bg-[#1C2333] px-1.5 py-0.5 rounded">
                변경
              </span>
            </div>
          ) : (
            <div
              className={`flex flex-col items-center justify-center h-16 border-2 border-dashed border-[#E5E8EB] dark:border-[#2D3748] rounded-lg hover:border-[#3182F6] transition-colors ${uploadingProduct ? "opacity-60" : ""}`}
            >
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

// ── 메인 ──────────────────────────────────────────────────────────────────────

export default function GeneratorChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [partial, setPartial] = useState<PartialRequest>({});
  const [progress, setProgress] = useState<{ pct: number; message: string } | null>(null);
  const [generationId, setGenerationId] = useState<string | null>(null);
  const [generationDone, setGenerationDone] = useState(false);

  const [brandLogoKey, setBrandLogoKey] = useState<string | null>(null);
  const [brandLogoPreview, setBrandLogoPreview] = useState<string | null>(null);
  const [productImageKey, setProductImageKey] = useState<string | null>(null);
  const [productImagePreview, setProductImagePreview] = useState<string | null>(null);
  const [uploadingLogo, setUploadingLogo] = useState(false);
  const [uploadingProduct, setUploadingProduct] = useState(false);

  const sessionIdRef = useRef<string | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // 세션 초기화 — localStorage에서 복원하거나 새로 생성
  useEffect(() => {
    const stored = localStorage.getItem(SESSION_KEY);
    if (stored) {
      sessionIdRef.current = stored;
      // 서버에서 이전 세션 상태 복원 시도
      fetch(`${API_BASE}/api/generator/chat/sessions/${stored}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (data) {
            setMessages(data.messages ?? []);
            setPartial(data.partial_request ?? {});
            if (data.generation_id) {
              setGenerationId(data.generation_id);
              setGenerationDone(data.status === "generating");
            }
          }
        })
        .catch(() => {
          // 세션 만료 → 새로 생성
          createSession();
        });
    } else {
      createSession();
    }
    return () => esRef.current?.close();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, progress]);

  async function createSession() {
    const res = await fetch(`${API_BASE}/api/generator/chat/sessions`, { method: "POST" });
    const data = await res.json();
    sessionIdRef.current = data.session_id;
    localStorage.setItem(SESSION_KEY, data.session_id);
  }

  async function handleLogoChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !sessionIdRef.current) return;
    setUploadingLogo(true);
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch(`${API_BASE}/api/generator/logo`, {
        method: "POST",
        headers: { "x-client-id": sessionIdRef.current },
        body: formData,
      });
      if (!res.ok) return;
      const data = await res.json();
      setBrandLogoKey(data.key);
      setBrandLogoPreview(`${API_BASE}${data.url}`);
    } finally {
      setUploadingLogo(false);
      e.target.value = "";
    }
  }

  async function handleProductChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingProduct(true);
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch(`${API_BASE}/api/generator/product-image`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) return;
      const data = await res.json();
      setProductImageKey(data.temp_key);
      setProductImagePreview(URL.createObjectURL(file));
    } finally {
      setUploadingProduct(false);
      e.target.value = "";
    }
  }

  function subscribeSSE(genId: string) {
    esRef.current?.close();
    const es = new EventSource(`${API_BASE}/api/generator/generations/${genId}/stream`);
    esRef.current = es;

    es.onmessage = (e) => {
      const data = JSON.parse(e.data) as SSEEvent;
      if (data.event === "progress") {
        setProgress({ pct: data.pct ?? 0, message: data.message ?? "" });
      } else if (data.event === "completed") {
        setProgress(null);
        setGenerationDone(true);
        es.close();
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: `광고 생성이 완료됐어요. 결과를 확인하러 가볼까요?`,
          },
        ]);
      } else if (data.event === "error") {
        setProgress(null);
        es.close();
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: `생성 중 오류가 발생했어요: ${data.message}` },
        ]);
      }
    };
    es.onerror = () => {
      setProgress(null);
      es.close();
    };
  }

  async function handleSend(text?: string) {
    const content = text ?? input.trim();
    if (!content || loading || !sessionIdRef.current) return;

    setMessages((prev) => [...prev, { role: "user", content }]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(
        `${API_BASE}/api/generator/chat/sessions/${sessionIdRef.current}/messages`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            content,
            brand_logo_s3_key: brandLogoKey ?? undefined,
            product_image_temp_key: productImageKey ?? undefined,
          }),
        }
      );

      if (!res.ok) {
        throw new Error("서버 오류");
      }

      const data: SendResult = await res.json();
      setPartial(data.partial_request);
      setMessages((prev) => [...prev, { role: "assistant", content: data.response }]);

      if (data.generation_id) {
        setGenerationId(data.generation_id);
        subscribeSSE(data.generation_id);
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "서버에 연결할 수 없어요. 잠시 후 다시 시도해주세요." },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleReset() {
    esRef.current?.close();
    localStorage.removeItem(SESSION_KEY);
    setMessages([]);
    setPartial({});
    setProgress(null);
    setGenerationId(null);
    setGenerationDone(false);
    setBrandLogoKey(null);
    setBrandLogoPreview(null);
    setProductImageKey(null);
    setProductImagePreview(null);
    createSession();
  }

  const hasPartial = Object.values(partial).some(Boolean);

  return (
    <AppLayout>
      <div className="h-screen bg-white dark:bg-[#0F1117] flex transition-colors overflow-hidden">
        {/* ── 채팅 영역 ── */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* 헤더 */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-[#E5E8EB] dark:border-[#2D3748]">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 flex items-center justify-center rounded-lg bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6]">
                <SparkleIcon />
              </div>
              <h1 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">광고 생성 도우미</h1>
            </div>
            <button
              onClick={handleReset}
              className="text-xs text-[#8B95A1] dark:text-[#6B7280] hover:text-[#3182F6] transition-colors"
            >
              새 대화
            </button>
          </div>

          {/* 메시지 목록 */}
          <div className="flex-1 overflow-y-auto">
            {messages.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center h-full px-4 pb-20">
                <div className="mb-3 w-12 h-12 flex items-center justify-center rounded-2xl bg-[#EBF3FF] dark:bg-[#1E3A5F]">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#3182F6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 17l-6.2 4.3 2.4-7.4L2 9.4h7.6z" />
                  </svg>
                </div>
                <h2 className="text-lg font-bold text-[#191F28] dark:text-[#F2F4F6] mb-2">광고를 만들어드릴게요</h2>
                <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] text-center leading-relaxed mb-8">
                  상품 이름부터 시작해보세요.<br />대화로 정보를 모아 광고를 자동 생성합니다.
                </p>
                <div className="grid grid-cols-1 gap-2 w-full max-w-xs">
                  {[
                    "비타민 음료 광고 만들어줘",
                    "운동화 브랜드 인스타 광고 해줘",
                    "카페 신메뉴 홍보 광고 만들어줘",
                  ].map((prompt) => (
                    <button
                      key={prompt}
                      onClick={() => handleSend(prompt)}
                      className="px-4 py-3 text-left text-sm text-[#4E5968] dark:text-[#9CA3AF] bg-[#F9FAFB] dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl hover:border-[#3182F6] hover:text-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-all"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="max-w-2xl mx-auto px-4 py-6 space-y-5">
                {messages.map((msg, i) => (
                  <div
                    key={i}
                    className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                  >
                    {msg.role === "assistant" && (
                      <div className="w-7 h-7 shrink-0 flex items-center justify-center rounded-lg bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6] mt-1">
                        <SparkleIcon />
                      </div>
                    )}
                    <div
                      className={`max-w-sm px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
                        msg.role === "user"
                          ? "bg-[#3182F6] text-white rounded-br-md"
                          : "bg-[#F2F4F6] dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6] rounded-bl-md"
                      }`}
                    >
                      {msg.content}
                    </div>
                  </div>
                ))}

                {/* 진행률 카드 */}
                {progress && (
                  <div className="flex gap-3 justify-start">
                    <div className="w-7 h-7 shrink-0 flex items-center justify-center rounded-lg bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6] mt-1">
                      <SparkleIcon />
                    </div>
                    <ProgressCard pct={progress.pct} message={progress.message} />
                  </div>
                )}

                {/* 생성 완료 — 결과 이동 버튼 */}
                {generationDone && generationId && (
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

                {/* 로딩 */}
                {loading && <TypingIndicator />}

                <div ref={bottomRef} />
              </div>
            )}
          </div>

          {/* 입력창 */}
          <div className="border-t border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#1C2333] px-4 py-4 transition-colors">
            <div className="max-w-2xl mx-auto flex items-end gap-3">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                placeholder="메시지를 입력하세요... (Shift+Enter로 줄바꿈)"
                rows={1}
                disabled={loading || !!progress}
                className="flex-1 px-4 py-3 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] text-sm text-[#191F28] dark:text-[#F2F4F6] placeholder-[#B0B8C1] dark:placeholder-[#4B5563] focus:outline-none focus:border-[#3182F6] focus:ring-2 focus:ring-[#3182F6]/10 transition-colors resize-none bg-white dark:bg-[#252D3D] leading-relaxed disabled:opacity-60"
                style={{ maxHeight: "120px" }}
              />
              <button
                onClick={() => handleSend()}
                disabled={!input.trim() || loading || !!progress}
                className="p-3 bg-[#3182F6] text-white rounded-xl hover:bg-[#1B6EEB] disabled:opacity-30 disabled:cursor-not-allowed transition-all shrink-0"
              >
                <SendIcon />
              </button>
            </div>
          </div>
        </div>

        {/* ── 정보 수집 패널 (우측) ── */}
        <div className="w-64 shrink-0 border-l border-[#E5E8EB] dark:border-[#2D3748] p-4 overflow-y-auto space-y-3">
          <UploadPanel
            sessionId={sessionIdRef.current}
            brandLogoPreview={brandLogoPreview}
            productImagePreview={productImagePreview}
            uploadingLogo={uploadingLogo}
            uploadingProduct={uploadingProduct}
            onLogoChange={handleLogoChange}
            onProductChange={handleProductChange}
          />

          {hasPartial && <InfoCard partial={partial} />}

          {generationId && (
            <a
              href={`/generations/${generationId}`}
              className="block text-center text-xs text-[#3182F6] hover:underline"
            >
              생성 결과 보기
            </a>
          )}
        </div>
      </div>
    </AppLayout>
  );
}
