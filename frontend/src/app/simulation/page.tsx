"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import AppLayout from "@/components/AppLayout";
import { useProjects } from "@/components/ProjectContext";
import { SimulatorProgress } from "@/components/simulator/SimulatorProgress";
import { DistributionChart } from "@/components/ui/DistributionChart";
import { KpiCard } from "@/components/ui/KpiCard";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { formatPercent } from "@/lib/utils";
import { api } from "@/lib/api";
import type { SimulationResult, SSEProgressEvent } from "@/lib/types";

type Step = "setup" | "running" | "result";
type InputMode = "image" | "text";
type Objective = "awareness" | "conversion" | "lead_gen" | "app_install" | "retention" | "product_launch" | "promotion";
type Gender = "여성" | "남성";
type AgeGroup = "20대" | "30대" | "40대" | "50대" | "50+";
type BudgetScale = "소규모" | "중간" | "대규모";
type CompetitionLevel = "블루오션" | "보통" | "레드오션";

const OBJECTIVES: { value: Objective; label: string }[] = [
  { value: "awareness",      label: "브랜드 인지" },
  { value: "conversion",     label: "구매 전환" },
  { value: "lead_gen",       label: "리드 수집" },
  { value: "app_install",    label: "앱 설치" },
  { value: "retention",      label: "재구매 유도" },
  { value: "product_launch", label: "신제품 런칭" },
  { value: "promotion",      label: "프로모션 반응" },
];

const AGE_GROUPS: AgeGroup[] = ["20대", "30대", "40대", "50대", "50+"];

const TRADEMARK_KINDS: Record<number, string> = {
  1:"화학제품, 비료, 코팅제, 비닐", 2:"페인트, 니스, 래커, 잉크, 염료",
  3:"화장품, 향수, 디퓨져, 비누, 세면용품, 세탁세제", 4:"양초, 향초, 램프",
  5:"의약제, 살균제, 제초제", 6:"금속재료, 건축재료",
  7:"기계 및 공작기계, 모터 및 엔진, 농기구, 자동판매기", 8:"수공구, 수동기구, 칼",
  9:"컴퓨터, 소프트웨어, CD, DVD, USB, 핸드폰 악세서리, 카메라", 10:"의료용 기계기구, 의료재료",
  11:"조명장치, 조리장치, 냉난방장치", 12:"자동차, 비행기, 선박, 수송기계기구",
  13:"총포탄, 화약류, 불꽃", 14:"귀금속, 보석류, 시계", 15:"악기",
  16:"서적, 인쇄물, 잡지, 사진, 문방구, 미술재료, 교육재료",
  17:"고무, 플라스틱 제품, 충전·방음·단열·절연재료",
  18:"가죽, 인조가죽 제품, 트렁크 및 여행용 가방, 우산, 양산",
  19:"비금속제 건축재료, 비금속제 이동식 건축물, 비금속제 기념물",
  20:"가구, 쿠션, 액자, 목재, 인테리어 장식품",
  21:"가정용품, 주방용 기구, 용기, 스펀지, 솔, 청소용구, 유리, 도자기 제품",
  22:"로프, 끈, 망, 텐트, 차양막, 타폴린, 돛, 충전용 재료", 23:"직물용 실(絲)",
  24:"직물, 직물제품, 침대커버, 테이블커버", 25:"의류, 신발, 모자",
  26:"레이스, 자수포, 리본, 단추, 핀, 바늘, 조화(造花)",
  27:"카펫, 매트, 리놀륨, 비직물제 벽걸이",
  28:"장난감, 게임기, 오락 및 놀이용구, 체조용품 및 운동용품",
  29:"육류, 어류, 절임, 조림, 냉동, 건조, 조리된 식품, 계란, 우유, 유제품",
  30:"커피, 차(茶), 쌀, 빵, 과자, 빙과, 소금, 소스(조미료), 향신료",
  31:"곡물, 농업·원예·임산물, 신선과일 및 채소, 종자, 식물, 사료",
  32:"맥주, 광천수, 탄산수, 음료, 과실음료 및 과실주스",
  33:"와인, 소주, 위스키, 탁주, 담금주", 34:"담배, 흡연용품, 성냥",
  35:"통신판매업, 온라인쇼핑몰, 광고업, 각종도소매업, 컨설팅, 무역업",
  36:"보험업, 임대업, 분양업, 투자자문업, 금융업, 부동산업, 할부리스업",
  37:"건축건설업, 자동차정비업, 인테리어, 수리업, 세탁업, 청소업",
  38:"통신업, 방송업, 인터넷방송, 데이터전송업, 온라인컨텐츠 전송업",
  39:"운송업, 여행예약, 관광업, 택배업, 이사대행, 견인업, 차량임대업, 창고업",
  40:"인쇄제본업, 목공업, 제분업, 식품가공, 소재가공업",
  41:"학원, 교육, 출판, 연예, 유학알선, 피트니스, 스포츠, 게임, 공연문화활동업",
  42:"프로그래밍업, 웹·제품·건축 디자인업, 과학·기술 R&D 연구소",
  43:"카페, 요식업, 베이커리, 주점업, 숙박업, 식품조달",
  44:"병원, 약국, 심리상담, 피부관리, 미용실, 네일샵, 사우나, 꽃꽂이, 산후조리",
  45:"법무, 보안, 웨딩, 장례, 종교, 돌봄서비스, 서비스업, 온라인 소셜네트워킹",
};

const TRADEMARK_CATEGORIES = [
  { name: "전체분류", classes: [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45] },
  { name: "요식업/식음료",            classes: [5,9,21,29,30,31,32,33,35,39,40,41,43,44] },
  { name: "의류/패션/쇼핑몰",         classes: [9,14,18,23,24,25,26,28,35,40,41,42,45] },
  { name: "뷰티/미용/화장품",         classes: [3,4,5,8,10,11,21,26,35,41,42,44] },
  { name: "의료/제약/복지",           classes: [3,5,10,29,35,36,40,41,42,43,44,45] },
  { name: "여행/스포츠/취미",         classes: [9,11,12,15,18,21,22,24,25,28,35,39,41,43] },
  { name: "교육/엔터테인먼트/유튜버", classes: [9,16,21,25,28,35,38,41,42] },
  { name: "생활/편의서비스",          classes: [9,35,36,37,38,39,40,41,42,43,44,45] },
  { name: "생활용품/가구/가전제품",   classes: [3,4,5,7,8,9,11,16,20,21,24,27,35] },
  { name: "출산/유아동",             classes: [3,5,9,10,12,16,18,20,21,24,25,27,28,30,35,41] },
  { name: "반려/애완용품",           classes: [3,5,6,9,12,16,18,20,21,28,31,35,41,43,44,45] },
  { name: "차량/오토",               classes: [1,3,4,5,9,12,17,27,28,35,37,39,43] },
  { name: "인테리어/건축/부동산",     classes: [2,6,11,17,19,20,27,35,36,37,40,42] },
  { name: "과학/환경/법률",          classes: [1,2,4,7,9,11,12,35,37,39,40,42,44,45] },
  { name: "IT/플랫폼/APP",           classes: [7,9,12,35,36,37,38,39,41,42,44,45] },
];

/* ─── 공통 레이블 클래스 ─── */
const labelCls = "block text-xs font-semibold text-[#4E5968] dark:text-[#9CA3AF] mb-1.5";
const sectionTitle = "text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-2";
const chipBase = "px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors";
const chipActive = "border-[#3182F6] bg-[#EEF4FF] dark:bg-[#1E3A5F] text-[#3182F6]";
const chipIdle = "border-[#E5E8EB] dark:border-[#2D3748] text-[#8B95A1] dark:text-[#6B7280] hover:border-[#3182F6]";
const inputCls = "w-full px-3 py-2.5 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#252D3D] text-sm text-[#191F28] dark:text-[#F2F4F6] focus:outline-none focus:ring-2 focus:ring-[#3182F6] placeholder:text-[#B0B8C1] dark:placeholder:text-[#4B5563] transition-colors";

export default function SimulationPage() {
  const router = useRouter();
  const { selectedProject, refreshDetails } = useProjects();
  const [step, setStep] = useState<Step>("setup");
  const [inputMode, setInputMode] = useState<InputMode>("image");
  const [file, setFile] = useState<File | null>(null);
  const [adTitle, setAdTitle] = useState("");
  const [adDescription, setAdDescription] = useState("");
  const [textInput, setTextInput] = useState({ headline: "", body: "", cta: "" });
  const [personaCount, setPersonaCount] = useState(20);
  const [objectives, setObjectives] = useState<Objective[]>([]);
  const [adCategory, setAdCategory] = useState("");
  const [adClass, setAdClass] = useState<number | null>(null);
  const [targetGenders, setTargetGenders] = useState<Gender[]>([]);
  const [targetAges, setTargetAges] = useState<AgeGroup[]>([]);
  const [budgetScale, setBudgetScale] = useState<BudgetScale | null>(null);
  const [competitionLevel, setCompetitionLevel] = useState<CompetitionLevel | null>(null);
  const [progress, setProgress] = useState({ stage: "", pct: 0, message: "" });
  const [result, setResult] = useState<SimulationResult | null>(null);

  const toggle = <T,>(setter: React.Dispatch<React.SetStateAction<T[]>>, val: T) =>
    setter((prev) => prev.includes(val) ? prev.filter((x) => x !== val) : [...prev, val]);

  const canStart = !!selectedProject && (inputMode === "image" ? !!file : !!textInput.headline);

  async function startSimulation() {
    setStep("running");
    setProgress({ stage: "ad_analysis", pct: 5, message: "광고 분석 중..." });
    try {
      let adAnalysis: unknown;
      if (inputMode === "image" && file) {
        const uploadRes = await api.ads.upload(file, "default") as { ad_id: string; s3_url: string };
        adAnalysis = await api.ads.analyzeImage({ ad_id: uploadRes.ad_id, image_url: uploadRes.s3_url });
      } else {
        adAnalysis = await api.ads.analyzeText({
          ad_id: crypto.randomUUID(),
          text_content: { headline: textInput.headline, body: textInput.body, cta: textInput.cta },
        });
      }
      const simRes = await api.simulate.start({
        simulation_id: crypto.randomUUID(),
        ad_analysis: adAnalysis,
        objective: objectives[0] ?? "conversion",
        persona_set: { id: crypto.randomUUID(), size: personaCount, composition: {} },
        project_id: selectedProject?.id ?? null,
        ad_title: adTitle || textInput.headline || "광고 시뮬레이션",
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
          if (selectedProject?.id) refreshDetails(selectedProject.id);
        } else if (data.event === "error") {
          es.close();
          setStep("setup");
        }
      };
    } catch {
      setStep("setup");
    }
  }

  /* ─── STEP: setup (upload + config 통합 2열) ─── */
  if (step === "setup") {
    const previewUrl = file ? URL.createObjectURL(file) : null;

    return (
      <AppLayout>
        <div className="px-8 py-8 max-w-5xl mx-auto">
          <div className="mb-6">
            <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">광고 시뮬레이션</h1>
            <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">AI 가상 소비자에게 광고를 테스트하고 성과를 예측합니다</p>
          </div>

          {/* 프로젝트 선택 상태 */}
          {selectedProject ? (
            <div className="flex items-center gap-2 mb-5 px-4 py-2.5 bg-[#EBF3FF] dark:bg-[#1E3A5F] rounded-xl border border-[#BFDBFE] dark:border-[#1E40AF]">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#3182F6" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
              </svg>
              <span className="text-sm font-medium text-[#3182F6]">{selectedProject.name}</span>
              <span className="text-xs text-[#60A5FA] ml-1">프로젝트에 시뮬레이션이 저장됩니다</span>
            </div>
          ) : (
            <div className="flex items-center gap-2 mb-5 px-4 py-2.5 bg-[#FFFBEB] dark:bg-[#422006] rounded-xl border border-[#FDE68A] dark:border-[#78350F]">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#D97706" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <span className="text-sm text-[#D97706] dark:text-[#FCD34D]">왼쪽 패널에서 프로젝트를 선택해야 시뮬레이션을 실행할 수 있습니다</span>
            </div>
          )}


          <div className="grid grid-cols-[1fr_1fr] gap-5 items-start">

            {/* ── 왼쪽: 광고 입력 ── */}
            <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6 flex flex-col gap-5 transition-colors">
              <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">광고 소재</p>

              {/* 탭 */}
              <div className="flex gap-2">
                {(["image", "text"] as InputMode[]).map((m) => (
                  <button
                    key={m}
                    onClick={() => setInputMode(m)}
                    className={`px-4 py-2 rounded-lg text-xs font-medium transition-colors ${
                      inputMode === m
                        ? "bg-[#3182F6] text-white"
                        : "bg-[#F2F4F6] dark:bg-[#252D3D] text-[#8B95A1] dark:text-[#6B7280] hover:bg-[#E5E8EB] dark:hover:bg-[#2D3748]"
                    }`}
                  >
                    {m === "image" ? "이미지 업로드" : "텍스트 입력"}
                  </button>
                ))}
              </div>

              {/* 이미지 모드 */}
              {inputMode === "image" ? (
                <div className="flex flex-col gap-3">
                  <label className="flex flex-col items-center justify-center h-52 border-2 border-dashed border-[#E5E8EB] dark:border-[#2D3748] rounded-xl cursor-pointer hover:border-[#3182F6] transition-colors relative overflow-hidden group">
                    {previewUrl ? (
                      <>
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={previewUrl} alt="미리보기" className="w-full h-full object-contain" />
                        <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center gap-2">
                          <svg className="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                          </svg>
                          <span className="text-xs text-white font-medium">클릭하여 변경</span>
                        </div>
                      </>
                    ) : (
                      <>
                        <svg className="w-10 h-10 text-[#B0B8C1] dark:text-[#4B5563] mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                        </svg>
                        <span className="text-sm text-[#8B95A1] dark:text-[#6B7280]">이미지 드래그 또는 클릭</span>
                        <span className="text-xs text-[#B0B8C1] dark:text-[#4B5563] mt-1">JPG / PNG / WebP · 최대 10MB</span>
                      </>
                    )}
                    <input type="file" accept="image/*" className="hidden" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
                  </label>

                  {file && (
                    <div className="flex items-center gap-2 px-3 py-2 bg-[#F2F4F6] dark:bg-[#252D3D] rounded-lg">
                      <svg className="w-4 h-4 text-[#3182F6] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <span className="text-xs text-[#4E5968] dark:text-[#9CA3AF] truncate flex-1">{file.name}</span>
                      <button onClick={() => setFile(null)} className="text-[#B0B8C1] hover:text-[#F74D4D] transition-colors shrink-0">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                  )}

                  {/* 이미지 모드 전용: 광고 제목 */}
                  <div>
                    <label className={labelCls}>광고 제목 <span className="text-[#F74D4D]">*</span></label>
                    <input type="text" value={adTitle} onChange={(e) => setAdTitle(e.target.value)}
                      placeholder="광고 제목을 입력하세요" className={inputCls} />
                  </div>
                </div>
              ) : (
                /* 텍스트 모드 */
                <div className="flex flex-col gap-4">
                  {(["headline", "body", "cta"] as const).map((field) => (
                    <div key={field}>
                      <label className={labelCls}>
                        {field === "headline" ? <>헤드라인 <span className="text-[#F74D4D]">*</span></> : field === "body" ? "본문" : "CTA (행동 유도 문구)"}
                      </label>
                      {field === "body" ? (
                        <textarea value={textInput[field]} onChange={(e) => setTextInput((p) => ({ ...p, [field]: e.target.value }))}
                          rows={5} placeholder="광고 본문을 입력하세요..."
                          className={`${inputCls} resize-none`} />
                      ) : (
                        <input type="text" value={textInput[field]} onChange={(e) => setTextInput((p) => ({ ...p, [field]: e.target.value }))}
                          placeholder={field === "headline" ? "강렬한 헤드라인을 입력하세요..." : "클릭 유도 문구 (예: 지금 시작하기)"}
                          className={inputCls} />
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* 광고 설명 (공통) */}
              <div>
                <label className={labelCls}>광고 설명 <span className="text-[10px] text-[#B0B8C1] dark:text-[#4B5563]">선택사항</span></label>
                <textarea value={adDescription} onChange={(e) => setAdDescription(e.target.value)}
                  rows={3} placeholder="광고에 대한 추가 설명을 입력하세요"
                  className={`${inputCls} resize-none`} />
              </div>
            </div>

            {/* ── 오른쪽: 시뮬레이션 설정 ── */}
            <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6 flex flex-col gap-5 transition-colors">
              <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">시뮬레이션 설정</p>

              {/* 페르소나 수 */}
              <div className="bg-[#F9FAFB] dark:bg-[#252D3D] border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl px-4 py-4">
                <label className={labelCls}>페르소나 수: <span className="text-[#3182F6] font-bold">{personaCount}명</span></label>
                <input type="range" min={10} max={50} value={personaCount}
                  onChange={(e) => setPersonaCount(Number(e.target.value))}
                  className="w-full accent-[#3182F6] mt-1" />
                <div className="flex justify-between text-[10px] text-[#B0B8C1] dark:text-[#4B5563] mt-1">
                  <span>10명</span><span>50명</span>
                </div>
              </div>

              <hr className="border-[#E5E8EB] dark:border-[#2D3748]" />

              {/* 광고 타겟 */}
              <div>
                <p className={sectionTitle}>광고 타겟 <span className="text-[10px] font-normal text-[#B0B8C1] dark:text-[#4B5563]">선택사항</span></p>
                <div className="space-y-2">
                  <div>
                    <p className="text-[10px] text-[#8B95A1] dark:text-[#6B7280] mb-1.5">성별</p>
                    <div className="flex gap-2">
                      {(["여성", "남성"] as Gender[]).map((g) => (
                        <button key={g} type="button" onClick={() => toggle(setTargetGenders, g)}
                          className={`${chipBase} ${targetGenders.includes(g) ? chipActive : chipIdle}`}>{g}</button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <p className="text-[10px] text-[#8B95A1] dark:text-[#6B7280] mb-1.5">연령대</p>
                    <div className="flex flex-wrap gap-2">
                      {AGE_GROUPS.map((a) => (
                        <button key={a} type="button" onClick={() => toggle(setTargetAges, a)}
                          className={`${chipBase} ${targetAges.includes(a) ? chipActive : chipIdle}`}>{a}</button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              <hr className="border-[#E5E8EB] dark:border-[#2D3748]" />

              {/* 캠페인 목표 */}
              <div>
                <p className={sectionTitle}>캠페인 목표</p>
                <div className="flex flex-wrap gap-2">
                  {OBJECTIVES.map(({ value, label }) => (
                    <button key={value} type="button" onClick={() => toggle(setObjectives, value)}
                      className={`${chipBase} ${objectives.includes(value) ? chipActive : chipIdle}`}>{label}</button>
                  ))}
                </div>
              </div>

              <hr className="border-[#E5E8EB] dark:border-[#2D3748]" />

              {/* 광고 카테고리 */}
              <div>
                <p className={sectionTitle}>광고 카테고리 <span className="text-[10px] font-normal text-[#B0B8C1] dark:text-[#4B5563]">선택사항</span></p>
                <div className="space-y-2">
                  <select value={adCategory} onChange={(e) => { setAdCategory(e.target.value); setAdClass(null); }}
                    className={inputCls}>
                    <option value="">카테고리 선택</option>
                    {TRADEMARK_CATEGORIES.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
                  </select>
                  <select value={adClass ?? ""} onChange={(e) => setAdClass(e.target.value ? Number(e.target.value) : null)}
                    disabled={!adCategory} className={`${inputCls} disabled:opacity-40 disabled:cursor-not-allowed`}>
                    <option value="">{adCategory ? "분류 선택 (선택사항)" : "카테고리를 먼저 선택하세요"}</option>
                    {(TRADEMARK_CATEGORIES.find((c) => c.name === adCategory)?.classes ?? []).map((n) => (
                      <option key={n} value={n}>{n}류 — {TRADEMARK_KINDS[n]}</option>
                    ))}
                  </select>
                  {adClass !== null && (
                    <p className="text-xs text-[#3182F6] bg-[#EEF4FF] dark:bg-[#1E3A5F] px-3 py-2 rounded-lg">
                      {adClass}류: {TRADEMARK_KINDS[adClass]}
                    </p>
                  )}
                </div>
              </div>

              <hr className="border-[#E5E8EB] dark:border-[#2D3748]" />

              {/* 예산 + 경쟁 */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className={sectionTitle}>예산 규모 <span className="text-[10px] font-normal text-[#B0B8C1] dark:text-[#4B5563]">선택</span></p>
                  <div className="flex gap-1.5">
                    {(["소규모", "중간", "대규모"] as BudgetScale[]).map((v) => (
                      <button key={v} type="button" onClick={() => setBudgetScale(budgetScale === v ? null : v)}
                        className={`flex-1 py-2 rounded-lg border text-[10px] font-medium transition-colors ${budgetScale === v ? chipActive : chipIdle}`}>{v}</button>
                    ))}
                  </div>
                </div>
                <div>
                  <p className={sectionTitle}>경쟁 강도 <span className="text-[10px] font-normal text-[#B0B8C1] dark:text-[#4B5563]">선택</span></p>
                  <div className="flex gap-1.5">
                    {(["블루오션", "보통", "레드오션"] as CompetitionLevel[]).map((v) => (
                      <button key={v} type="button" onClick={() => setCompetitionLevel(competitionLevel === v ? null : v)}
                        className={`flex-1 py-2 rounded-lg border text-[10px] font-medium transition-colors ${competitionLevel === v ? chipActive : chipIdle}`}>{v}</button>
                    ))}
                  </div>
                </div>
              </div>

              {/* 시뮬레이션 시작 버튼 */}
              <button
                onClick={startSimulation}
                disabled={!canStart || (inputMode === "image" && !adTitle)}
                className="mt-2 w-full flex items-center justify-center gap-2 py-3 bg-[#3182F6] hover:bg-[#1B6EEB] disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl text-sm font-semibold transition-colors"
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
        <div className="px-8 py-8 max-w-5xl mx-auto">
          <div className="mb-6">
            <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">시뮬레이션 진행 중</h1>
            <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">잠시만 기다려주세요</p>
          </div>
          <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6 max-w-2xl transition-colors">
            <SimulatorProgress currentStage={progress.stage} pct={progress.pct} message={progress.message} />
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
        <div className="px-8 py-8 max-w-5xl mx-auto space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">시뮬레이션 결과</h1>
              <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">AI 가상 소비자 {p0.persona_reactions.length}명의 반응</p>
            </div>
            <button onClick={() => { setStep("setup"); setResult(null); }}
              className="px-4 py-2 border border-[#E5E8EB] dark:border-[#2D3748] rounded-lg text-sm text-[#8B95A1] dark:text-[#6B7280] hover:bg-[#F9FAFB] dark:hover:bg-[#252D3D] transition-colors">
              새 시뮬레이션
            </button>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiCard label="CTR 예측" value={formatPercent(p1.kpi.ctr)} />
            <KpiCard label="CVR 예측" value={formatPercent(p1.kpi.cvr)} />
            <KpiCard label="순 호감도" value={formatPercent((p1.kpi.net_sentiment + 1) / 2)} />
            <KpiCard label="참여 페르소나" value={`${p0.persona_reactions.length}명`} />
          </div>

          <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6 transition-colors">
            <DistributionChart title="집단 구매의향 분포" distribution={p0.aggregate_purchase_intent} kobacoBadge={p0.kobaco_comparable} />
          </div>

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
