"use client";

import { useState } from "react";
import AppLayout from "@/components/AppLayout";
import { SimulatorProgress } from "@/components/simulator/SimulatorProgress";
import { DistributionChart } from "@/components/ui/DistributionChart";
import { KpiCard } from "@/components/ui/KpiCard";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { formatPercent } from "@/lib/utils";
import { api } from "@/lib/api";
import type { SimulationResult, SSEProgressEvent } from "@/lib/types";

type Step = "upload" | "config" | "running" | "result";
type InputMode = "image" | "text";

export default function SimulationPage() {
  const [step, setStep] = useState<Step>("upload");
  const [inputMode, setInputMode] = useState<InputMode>("image");
  const [file, setFile] = useState<File | null>(null);
  const [textInput, setTextInput] = useState({ headline: "", body: "", cta: "" });
  const [personaCount, setPersonaCount] = useState(20);
  const [objective, setObjective] = useState<"awareness" | "conversion">("conversion");
  const [progress, setProgress] = useState({ stage: "", pct: 0, message: "" });
  const [result, setResult] = useState<SimulationResult | null>(null);

  async function startSimulation() {
    setStep("running");
    setProgress({ stage: "ad_analysis", pct: 5, message: "광고 분석 중..." });

    try {
      let adAnalysis: unknown;

      if (inputMode === "image" && file) {
        // 1) 업로드
        const uploadRes = await api.ads.upload(file, "default") as { ad_id: string; s3_url: string };
        // 2) 이미지 분석
        adAnalysis = await api.ads.analyzeImage({ ad_id: uploadRes.ad_id, image_url: uploadRes.s3_url });
      } else {
        // 텍스트 분석
        adAnalysis = await api.ads.analyzeText({
          ad_id: crypto.randomUUID(),
          text_content: { headline: textInput.headline, body: textInput.body, cta: textInput.cta },
        });
      }

      const simRes = await api.simulate.start({
        simulation_id: crypto.randomUUID(),
        ad_analysis: adAnalysis,
        objective,
        persona_set: { id: crypto.randomUUID(), size: personaCount, composition: {} },
      }) as { task_id: string };

      const es = api.simulate.stream(simRes.task_id);
      es.onmessage = async (e) => {
        const data = JSON.parse(e.data) as SSEProgressEvent;
        if (data.event === "progress") {
          setProgress({ stage: data.stage ?? "", pct: data.pct ?? 0, message: data.message ?? "" });
        } else if (data.event === "completed") {
          es.close();
          const finalResult = await api.simulate.result(simRes.task_id) as SimulationResult;
          setResult(finalResult);
          setStep("result");
        } else if (data.event === "error") {
          es.close();
          setStep("upload");
        }
      };
    } catch {
      setStep("upload");
    }
  }

  /* ─── STEP: upload ─── */
  if (step === "upload") {
    const previewUrl = file ? URL.createObjectURL(file) : null;

    return (
      <AppLayout>
        <div className="px-8 py-8">
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">광고 시뮬레이션</h1>
            <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">
              AI 가상 소비자에게 광고를 테스트하고 성과를 예측합니다
            </p>
          </div>

          <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-8 w-full h-[700px] flex flex-col gap-6 transition-colors">
            {/* 탭 */}
            <div className="flex gap-2 border-b border-[#E5E8EB] dark:border-[#2D3748] pb-4 shrink-0">
              <button
                onClick={() => setInputMode("image")}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  inputMode === "image"
                    ? "bg-[#3182F6] text-white"
                    : "bg-[#F2F4F6] dark:bg-[#252D3D] text-[#8B95A1] dark:text-[#6B7280] hover:bg-[#E5E8EB] dark:hover:bg-[#2D3748]"
                }`}
              >
                이미지 업로드
              </button>
              <button
                onClick={() => setInputMode("text")}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  inputMode === "text"
                    ? "bg-[#3182F6] text-white"
                    : "bg-[#F2F4F6] dark:bg-[#252D3D] text-[#8B95A1] dark:text-[#6B7280] hover:bg-[#E5E8EB] dark:hover:bg-[#2D3748]"
                }`}
              >
                텍스트 입력
              </button>
            </div>

            {/* 입력 영역 — flex-1로 남은 공간 차지 */}
            {inputMode === "image" ? (
              <label className="flex flex-col items-center justify-center flex-1 border-2 border-dashed border-[#E5E8EB] dark:border-[#2D3748] rounded-xl cursor-pointer hover:border-[#3182F6] transition-colors relative overflow-hidden group">
                {previewUrl ? (
                  <>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={previewUrl}
                      alt="미리보기"
                      className="w-full h-full object-contain p-2"
                    />
                    <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center gap-2">
                      <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                      </svg>
                      <span className="text-sm text-white font-medium">클릭하여 변경</span>
                    </div>
                  </>
                ) : (
                  <>
                    <svg className="w-12 h-12 text-[#B0B8C1] dark:text-[#4B5563] mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                    </svg>
                    <span className="text-base text-[#8B95A1] dark:text-[#6B7280]">이미지 드래그 또는 클릭</span>
                    <span className="text-xs text-[#B0B8C1] dark:text-[#4B5563] mt-1">JPG / PNG / WebP · 최대 10MB</span>
                  </>
                )}
                <input
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                />
              </label>
            ) : (
              <div className="flex-1 overflow-y-auto space-y-4">
                {(["headline", "body", "cta"] as const).map((field) => (
                  <div key={field}>
                    <label className="text-xs font-medium text-[#8B95A1] dark:text-[#6B7280] mb-1.5 block uppercase tracking-wide">
                      {field === "headline" ? "헤드라인" : field === "body" ? "본문" : "CTA (행동 유도 문구)"}
                    </label>
                    {field === "body" ? (
                      <textarea
                        value={textInput[field]}
                        onChange={(e) => setTextInput((prev) => ({ ...prev, [field]: e.target.value }))}
                        rows={10}
                        placeholder="광고 본문을 입력하세요..."
                        className="w-full px-4 py-3 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#252D3D] text-sm text-[#191F28] dark:text-[#F2F4F6] focus:outline-none focus:ring-2 focus:ring-[#3182F6] placeholder:text-[#B0B8C1] dark:placeholder:text-[#4B5563] transition-colors resize-none"
                      />
                    ) : (
                      <input
                        type="text"
                        value={textInput[field]}
                        onChange={(e) => setTextInput((prev) => ({ ...prev, [field]: e.target.value }))}
                        placeholder={field === "headline" ? "강렬한 헤드라인을 입력하세요..." : "클릭 유도 문구 (예: 지금 시작하기)"}
                        className="w-full px-4 py-3 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#252D3D] text-sm text-[#191F28] dark:text-[#F2F4F6] focus:outline-none focus:ring-2 focus:ring-[#3182F6] placeholder:text-[#B0B8C1] dark:placeholder:text-[#4B5563] transition-colors"
                      />
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* 하단 고정 영역: 파일명 배지(이미지 모드) + 다음 단계 버튼 */}
            <div className="shrink-0 flex items-center justify-between gap-3">
              {inputMode === "image" && file ? (
                <div className="flex items-center gap-2 px-3 py-2 bg-[#F2F4F6] dark:bg-[#252D3D] rounded-lg min-w-0 flex-1">
                  <svg className="w-4 h-4 text-[#3182F6] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span className="text-sm text-[#4E5968] dark:text-[#9CA3AF] truncate">{file.name}</span>
                  <button
                    onClick={(e) => { e.preventDefault(); setFile(null); }}
                    className="ml-auto text-[#B0B8C1] hover:text-[#F74D4D] transition-colors shrink-0"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              ) : (
                <div className="flex-1" />
              )}
              <button
                onClick={() => setStep("config")}
                disabled={inputMode === "image" ? !file : !textInput.headline}
                className="flex items-center gap-2 px-6 py-3 bg-[#3182F6] hover:bg-[#1B6EEB] disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors shrink-0"
              >
                다음 단계
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </AppLayout>
    );
  }

  /* ─── STEP: config ─── */
  if (step === "config") {
    return (
      <AppLayout>
        <div className="px-8 py-8">
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">시뮬레이션 설정</h1>
            <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">페르소나 수와 캠페인 목표를 설정하세요</p>
          </div>

          <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-8 w-full h-[700px] overflow-y-auto space-y-6 transition-colors">
            {/* 페르소나 수 */}
            <div className="space-y-2">
              <label className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">
                페르소나 수: <span className="text-[#3182F6]">{personaCount}명</span>
              </label>
              <input
                type="range"
                min={10}
                max={50}
                value={personaCount}
                onChange={(e) => setPersonaCount(Number(e.target.value))}
                className="w-full accent-[#3182F6]"
              />
              <div className="flex justify-between text-xs text-[#B0B8C1] dark:text-[#4B5563]">
                <span>10명</span>
                <span>50명</span>
              </div>
            </div>

            {/* 캠페인 목표 */}
            <div className="space-y-2">
              <label className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">캠페인 목표</label>
              <div className="flex gap-3">
                {(["awareness", "conversion"] as const).map((obj) => (
                  <label
                    key={obj}
                    className={`flex items-center gap-2 px-4 py-2.5 rounded-xl border cursor-pointer transition-colors ${
                      objective === obj
                        ? "border-[#3182F6] bg-[#EEF4FF] dark:bg-[#1E3A5F] text-[#3182F6]"
                        : "border-[#E5E8EB] dark:border-[#2D3748] text-[#8B95A1] dark:text-[#6B7280] hover:border-[#3182F6]"
                    }`}
                  >
                    <input
                      type="radio"
                      name="objective"
                      value={obj}
                      checked={objective === obj}
                      onChange={() => setObjective(obj)}
                      className="hidden"
                    />
                    <span className="text-sm font-medium">
                      {obj === "awareness" ? "브랜드 인지" : "구매 전환"}
                    </span>
                  </label>
                ))}
              </div>
            </div>

            <div className="flex gap-3 pt-2">
              <button
                onClick={() => setStep("upload")}
                className="px-4 py-2.5 border border-[#E5E8EB] dark:border-[#2D3748] rounded-lg text-sm text-[#8B95A1] dark:text-[#6B7280] hover:bg-[#F9FAFB] dark:hover:bg-[#252D3D] transition-colors"
              >
                이전
              </button>
              <button
                onClick={startSimulation}
                className="flex items-center gap-2 px-6 py-2.5 bg-[#3182F6] hover:bg-[#1B6EEB] text-white rounded-lg text-sm font-medium transition-colors"
              >
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M8 5v14l11-7z" />
                </svg>
                시뮬레이션 시작
              </button>
            </div>
          </div>
        </div>
      </AppLayout>
    );
  }

  /* ─── STEP: running ─── */
  if (step === "running") {
    return (
      <AppLayout>
        <div className="max-w-screen-xl mx-auto px-6 py-8">
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">시뮬레이션 진행 중</h1>
            <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">잠시만 기다려주세요</p>
          </div>
          <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6 max-w-2xl transition-colors">
            <SimulatorProgress
              currentStage={progress.stage}
              pct={progress.pct}
              message={progress.message}
            />
          </div>
        </div>
      </AppLayout>
    );
  }

  /* ─── STEP: result ─── */
  if (step === "result" && result) {
    const { p0, p1 } = result;
    return (
      <AppLayout>
        <div className="max-w-screen-xl mx-auto px-6 py-8 space-y-6">
          {/* 헤더 */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">시뮬레이션 결과</h1>
              <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">AI 가상 소비자 {p0.persona_reactions.length}명의 반응</p>
            </div>
            <button
              onClick={() => { setStep("upload"); setResult(null); }}
              className="px-4 py-2 border border-[#E5E8EB] dark:border-[#2D3748] rounded-lg text-sm text-[#8B95A1] dark:text-[#6B7280] hover:bg-[#F9FAFB] dark:hover:bg-[#252D3D] transition-colors"
            >
              새 시뮬레이션
            </button>
          </div>

          {/* KPI 카드 */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiCard label="CTR 예측" value={formatPercent(p1.kpi.ctr)} />
            <KpiCard label="CVR 예측" value={formatPercent(p1.kpi.cvr)} />
            <KpiCard label="순 호감도" value={formatPercent((p1.kpi.net_sentiment + 1) / 2)} />
            <KpiCard label="참여 페르소나" value={`${p0.persona_reactions.length}명`} />
          </div>

          {/* 구매의향 분포 */}
          <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6 transition-colors">
            <DistributionChart
              title="집단 구매의향 분포"
              distribution={p0.aggregate_purchase_intent}
              kobacoBadge={p0.kobaco_comparable}
            />
          </div>

          {/* P1 신호 분포 */}
          <div>
            <h2 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-3">
              신호별 분포{" "}
              <span className="text-xs font-normal text-[#F4A100] bg-[#FFF8E6] dark:bg-[#2D2000] px-2 py-0.5 rounded-full ml-1">탐색적</span>
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {Object.entries(p1.signal_distributions)
                .filter(([k]) => k !== "conversion_intent")
                .map(([dim, dist]) => (
                  <div key={dim} className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-5 transition-colors">
                    <DistributionChart title={dim} distribution={dist.raw_probs} exploratory />
                  </div>
                ))}
            </div>
          </div>

          {/* 페르소나 반응 샘플 */}
          <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6 space-y-3 transition-colors">
            <h2 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">페르소나 반응 샘플</h2>
            {p0.persona_reactions.slice(0, 5).map((r) => (
              <div key={r.persona_id} className="text-sm text-[#4E5968] dark:text-[#9CA3AF] border-l-2 border-[#3182F6] pl-3 py-0.5">
                <span className="font-medium text-[#8B95A1] dark:text-[#6B7280] mr-1">{r.persona_id}</span>
                {r.free_text_reaction}
              </div>
            ))}
          </div>

          <Disclaimer />
        </div>
      </AppLayout>
    );
  }

  return null;
}
