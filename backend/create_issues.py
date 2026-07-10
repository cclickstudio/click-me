# 커밋엔 있으나 GitHub Issue가 없는 기능들을 일괄 등록하는 스크립트 (httpx + GitHub REST API)
"""
사용법:
    uv run python create_issues.py --dry-run   # 미리보기(생성 안 함)
    uv run python create_issues.py             # 실제 생성

토큰:
    환경변수 GITHUB_TOKEN 또는 GH_TOKEN 우선, 없으면 `gh auth token`을 자동 호출.
동작:
    기존 이슈(OPEN/CLOSED) 제목과 정확히 일치하면 건너뜀(중복 방지).
"""

import os
import subprocess
import sys

import httpx

REPO = "cclickstudio/click-me"
API = "https://api.github.com"

# 커밋 대조로 추려낸, 대응 이슈가 없는 구현 기능들.
ISSUES = [
    {
        "title": "[Simulation] AI 토론 파이프라인 (전문가4+일반인3·Judge·논제5개)",
        "labels": ["agent-simulation"],
        "body": (
            "집행 전 반응 예측을 위한 멀티에이전트 토론 파이프라인.\n\n"
            "- 패널 구성: 전문가 4 + 일반인 3\n"
            "- 최초 주제(headline) 고정, 논제 5개 생성, Judge 액션 강제\n"
            "- Judge 비용 최적화(라운드정리 Haiku·결론 1회 호출)\n\n"
            "근거 커밋: a5ca1ea, ff59415, 350a15a, dc0a63e"
        ),
    },
    {
        "title": "[Simulation] 토론 후 Q&A — 패널 순차 답변 SSE",
        "labels": ["agent-simulation"],
        "body": (
            "토론 종료 후 사용자 질문에 패널이 순차로 답변하는 Q&A 단계.\n\n"
            "- 입력 계약: question + reactions\n"
            "- 패널 순차 답변을 SSE로 스트리밍\n\n"
            "근거 커밋: f665abd, e98d71a, 7d067be"
        ),
    },
    {
        "title": "[Simulation] 일반인 토론자 선발 게이트 (타깃 적합·LLM 재랭킹·말투)",
        "labels": ["agent-simulation"],
        "body": (
            "토론에 투입할 일반인 토론자를 타깃에 맞춰 선발하는 게이트.\n\n"
            "- 타깃 밖 후보 배제(personas 인구통계), 전 연령형 보정\n"
            "- LLM 재랭킹 게이트 + 함정 테스트(선발 정확도 최우선)\n"
            "- 표현 다양성 위해 말투(tone) 부여\n\n"
            "근거 커밋: c713606, 4fb52c8, a071d62, 439afda, d13e638"
        ),
    },
    {
        "title": "[Simulation] 토론/Q&A LangSmith 단일 트레이스 묶기",
        "labels": ["agent-simulation"],
        "body": (
            "토론 1회와 Q&A를 각각 LangSmith 단일 트레이스로 묶어 관측성 확보.\n\n"
            "- @traceable 부모 run으로 LLM 호출 중첩\n"
            "- wrap_anthropic·wrap_openai로 토론 LLM 호출 트레이싱\n\n"
            "근거 커밋: 0e90a11, a3de5bd, 76a8b4c"
        ),
    },
    {
        "title": "[Frontend] 토론 패널 UI (SSE 스트림·논제 선택·Q&A 채팅)",
        "labels": ["frontend"],
        "body": (
            "토론 진행을 실시간으로 보여주는 프론트 패널.\n\n"
            "- DebatePanel SSE 스트림·결과 렌더\n"
            "- 논제 5개 선택, Q&A DM 채팅, 일반인 수 2/3/4 옵션\n\n"
            "근거 커밋: 788f8d5, 24f27e2, 0ea3bc8"
        ),
    },
    {
        "title": "[Backend] 제품 카테고리 NICE 분류 조회 API",
        "labels": ["backend"],
        "body": (
            "시뮬 입력 폼의 2단계 카테고리 선택을 위한 NICE 분류 조회 API.\n\n"
            "근거 커밋: daf52d8, c4986e9"
        ),
    },
    {
        "title": "[Management] 캠페인 목록·성과 대시보드 (CPM·CVR·시계열)",
        "labels": ["agent-management"],
        "body": (
            "집행 캠페인을 단일 창구에서 관리하는 대시보드.\n\n"
            "- 목록/카드 토글, 상세 시계열, 클릭 시 상세 모달\n"
            "- CPM·CVR 표시(conversions 합성)\n\n"
            "근거 커밋: 570b480, 43491b7, cc930f3, e7f39e1"
        ),
    },
    {
        "title": "[Management] 예산 관리 (게이지·경고·가드레일·한도)",
        "labels": ["agent-management"],
        "body": (
            "예산 소진을 추적하고 한도를 관리하는 화면·API.\n\n"
            "- /budget·/budget/limit 엔드포인트\n"
            "- 90/95/100% 가드레일, 게이지·경고·캠페인 분해\n\n"
            "근거 커밋: de64bc0, 203551a"
        ),
    },
    {
        "title": "[Management] 신규 캠페인 생성 HITL (제안→승인→생성)",
        "labels": ["agent-management"],
        "body": (
            "사람 검토(HITL)를 거치는 신규 캠페인 생성 흐름.\n\n"
            "- /campaigns/create-proposal 제안 엔드포인트(Tier3)\n"
            "- 폼→제안→승인→생성 화면\n\n"
            "근거 커밋: 9965bba, cf5b76d"
        ),
    },
    {
        "title": "[Management] 처방(Remediation) 에이전트 + 에스컬레이션 사다리",
        "labels": ["agent-management"],
        "body": (
            "성과 진단 후 처방 액션을 자율 결정하는 에이전트.\n\n"
            "- decide_action 결정 코어(진단+의향 → action 선택)\n"
            "- 타겟 범위 확장·입찰 전략 변경 등 처방 액션\n"
            "- 시간축 자동 에스컬레이션 사다리(remediation_escalations)\n"
            "- 처방 선택 정확도 eval\n\n"
            "근거 커밋: e37e781, e60fbc4, de0f860, bd65889, 9df15f4, 6bc5c06"
        ),
    },
    {
        "title": "[Management] 오가닉↔광고 비교·추천",
        "labels": ["agent-management"],
        "body": (
            "오가닉 게시물과 광고 성과를 비교해 추천 액션을 제시.\n\n"
            "- /compare·/compare/board 엔드포인트\n"
            "- ComparisonService.compare_and_recommend\n"
            "- 리프트 테이블 화면\n\n"
            "근거 커밋: 9377eb4, 168776a, 19f498f, 5f58cc2"
        ),
    },
    {
        "title": "[Management] Meta Marketing API 실연동 + 실시간 이상 감지",
        "labels": ["agent-management"],
        "body": (
            "Meta Marketing API 실연동과 실시간 캠페인 이상 감지.\n\n"
            "- 온보딩·권한 준비, KRW 예산 단위(offset=1) 검증\n"
            "- 실 캠페인 지표·감지 검증(meta_metrics_probe)\n"
            "- 실시간 이상 감지 관측 길이 정렬\n\n"
            "근거 커밋: b3dfbbc, affda78, 758d785, 7867f0d, c1b3d71"
        ),
    },
    # ══════════════════════════════════════════════════════════════
    # #96 이후 진행분 (PR #130~#183) — 발표 전 작업 이력 정리
    # ══════════════════════════════════════════════════════════════
    # ── 채팅 / 오케스트레이터 (agent-chat) ──
    {
        "title": "[Chat] 챗 숏텀 메모리 — 체크포인터 단일소스 + history 프리앰블 주입 + 라우터 연속성",
        "labels": ["agent-chat"],
        "body": (
            "대화 컨텍스트를 턴 넘어 유지하는 숏텀 메모리 도입.\n\n"
            "- load_context short_term을 state에서 파생(DB 조회 은퇴, 체크포인터 단일 소스)\n"
            "- 서브에이전트 어댑터가 대화 히스토리를 질문 프리앰블로 주입(sim·gen·mgmt)\n"
            "- 라우터 연속성 규칙 — 직전 되물음의 짧은 답을 같은 위임처로\n\n"
            "연결 PR: #143"
        ),
    },
    {
        "title": "[Chat] 챗 컨텍스트 영속 merge 리듀서(context_ids 턴 넘겨 생존) + E2E",
        "labels": ["agent-chat"],
        "body": (
            "광고 컨텍스트가 대화 턴을 넘겨 유지되도록 하는 리듀서.\n\n"
            "- context_ids merge 리듀서 — null 미덮어쓰기로 광고 컨텍스트 생존\n"
            "- 챗 컨텍스트 영속 E2E 테스트(merge 리듀서가 ad_id를 턴 넘겨 보존)\n\n"
            "연결 PR: #143"
        ),
    },
    {
        "title": "[Chat] 센터(Center) 통합 UI — 알림센터+채팅센터+필터, 플로팅 요소 일원화",
        "labels": ["agent-chat"],
        "body": (
            "흩어진 채팅·알림 진입점을 단일 센터로 통합.\n\n"
            "- 센터 shell(우측 접이식 채팅·알림 aside) + 필터 바(세그먼트·프로젝트)\n"
            "- 알림 센터(병합 목록·아코디언·상세·액션 이관) + 채팅 센터(세션 목록+라이브)\n"
            "- FloatingChat·ProjectChatSection·NotificationBell 제거(센터로 일원화)\n\n"
            "연결 PR: #159, #183"
        ),
    },
    {
        "title": "[Chat] 센터 제안 알림 자동생성 훅(시뮬↔제너 교차) + /api/center 병합조회",
        "labels": ["agent-chat"],
        "body": (
            "도메인 간 후속 제안을 알림으로 자동 생성.\n\n"
            "- 센터 제안 알림 자동생성 훅(시뮬→제너·제너→시뮬) + core 공용 헬퍼\n"
            "- 센터 알림 병합 조회 API(/api/center) + 통합 세션 목록 API(org 전체)\n\n"
            "연결 PR: #159"
        ),
    },
    {
        "title": "[Chat] LangSmith 표준화2 — 사용자 식별 메타·이미지 cost_usd·트레이스명 영문",
        "labels": ["agent-chat"],
        "body": (
            "LangSmith 관측을 사용자·비용 단위로 표준화.\n\n"
            "- 트레이스에 사용자 식별 메타 전파(chat·simulation·management·generator)\n"
            "- 이미지 생성 cost_usd 트레이스 기록, 트레이스명 영문 표준화\n"
            "- 챗 딥에이전트 트레이스를 표준 chat.assistant로 계측\n\n"
            "연결 PR: #130"
        ),
    },
    # ── 제너레이터 (agent-generator) ──
    {
        "title": "[Generator] 생성 자동 개선 루프(구조화 루프 + CLIO 위임 도구 + GenLoopWidget)",
        "labels": ["agent-generator"],
        "body": (
            "시안을 반복 평가·개선하는 자동 루프.\n\n"
            "- 생성 자동 개선 루프(구조화 루프 모듈) + CLIO 위임 도구\n"
            "- 자동 개선 루프 진행 카드(GenLoopWidget) + 소비자 반응 진단 표시\n"
            "- 시뮬 평가 옵션(최초 1회 시뮬로 개선 방향 확정) + KPI 등급 조기 종료\n\n"
            "연결 PR: #134, #151, #156"
        ),
    },
    {
        "title": "[Generator] 전략별 디자인 스타일 인덱싱(StyleProfile) + KB 타이포 폰트웨이트",
        "labels": ["agent-generator"],
        "body": (
            "전략에 맞춘 디자인 스타일을 인덱싱해 시안에 반영.\n\n"
            "- StyleProfile 1~3단계(floating·emotional 렌더, 리뷰카드·별점·숫자강조)\n"
            "- KB 타이포그래피 전략별 폰트 웨이트를 시안 렌더에 연결\n"
            "- 플랫폼 리레이아웃에 strategy 전파해 시안 스타일 유지\n\n"
            "연결 PR: #147"
        ),
    },
    {
        "title": "[Generator] Gemini 단일 호출 컴포즈 모드 + 이미지 전용 API 키 분리",
        "labels": ["agent-generator"],
        "body": (
            "Gemini로 이미지+텍스트를 한 번에 합성하는 컴포즈 모드.\n\n"
            "- Gemini 단일 호출 컴포즈 모드 + 이미지 전용 API 키 분리\n"
            "- Gemini 2.5 thinking 토큰이 카피 생성 출력을 잠식하는 문제 수정\n\n"
            "연결 PR: #147"
        ),
    },
    {
        "title": "[Generator] 채팅 생성 즉시 실행(SSE 진행카드) + 상품이미지 확인 게이트",
        "labels": ["agent-generator"],
        "body": (
            "채팅에서 광고 생성을 즉시 트리거하고 진행을 카드로 표시.\n\n"
            "- 채팅 생성 즉시 실행 + 진행 카드(SSE) — 자동화 Phase 1+2\n"
            "- 상품 이미지 의사 확인 게이트, 시안 카드 상세보기·라이트박스\n"
            "- 채팅 광고 생성 라우팅 — 정보 없어도 폼 도구 강제 호출, 목표 칩 선택\n\n"
            "연결 PR: #151, #182"
        ),
    },
    {
        "title": "[Generator] 생성 자동화 seam — LLM 재시도·provider 폴백·stuck 워커·품질 다이제스트",
        "labels": ["agent-generator"],
        "body": (
            "생성 파이프라인의 신뢰성·관측성 seam.\n\n"
            "- 생성 LLM 재시도·이미지 provider 폴백·자동화 seam\n"
            "- 생성 멈춤(stuck) 감지 워커 잡 + 품질 다이제스트 QA 통과율 집계\n"
            "- 제너레이터 페이지 서버 자동 점검 결과 표시\n\n"
            "연결 PR: #151"
        ),
    },
    {
        "title": "[Generator] 개선모드 상품 누끼 재사용 3-tier 폴백 + 5전략 동적선택 안정화",
        "labels": ["agent-generator"],
        "body": (
            "개선 모드에서 상품 이미지 누끼를 재사용하고 전략을 동적 선택.\n\n"
            "- 개선모드 상품 이미지 누끼 재사용 3-tier 폴백 안정화\n"
            "- 개선 모드 5전략 동적 선택 + floating/emotional 텍스트 가독성 개선\n"
            "- 전략 분류 크래시·provider 폴백·누끼 예외·S3 키 파싱 등 버그 수정\n\n"
            "연결 PR: #181, #156"
        ),
    },
    {
        "title": "[Generator] ads.generation_id 출처 기록(채팅 개선모드 누끼 역추적)",
        "labels": ["agent-generator"],
        "body": (
            "생성물의 출처를 기록해 개선 모드에서 역추적.\n\n"
            "- ads.generation_id 컬럼 — 생성 출처 기록\n"
            "- 시뮬 생성 시 generation_id 수신·영속('생성한 광고로 시뮬' 출처)\n"
            "- 채팅 개선모드 상품 누끼 재사용 — simulation→generation_id→누끼 키 역추적\n\n"
            "연결 PR: #156"
        ),
    },
    {
        "title": "[Generator] 발표용 생성 품질 측정 스크립트 6종(오타율·대비비·토큰비용·QA점수)",
        "labels": ["agent-generator"],
        "body": (
            "발표 근거용 생성 품질 정량 측정 도구.\n\n"
            "- 오타율·대비비·토큰비용·QA점수 측정 스크립트 6종\n"
            "- 계정/상품/프로젝트 필터, 검수 시트 빌드\n"
            "※ 일부는 feat/generator-yohan 브랜치에서 진행 중.\n\n"
            "연결 PR: #181"
        ),
    },
    # ── 시뮬레이션 (agent-simulation) ──
    {
        "title": "[Simulation] 3-모드 분석(전체합성·1명심층·세그먼트비교) 백+프론트",
        "labels": ["agent-simulation"],
        "body": (
            "시뮬 분석을 3가지 관점 모드로 제공.\n\n"
            "- 3-모드 분석(synthetic/individual/persona_set) 백엔드+프론트엔드\n"
            "- Persona Set 세그먼트 비교 — API·3-모드 선택 UI\n"
            "- 채팅 시뮬 위젯에 3-모드 분석 반영\n\n"
            "연결 PR: #144, #146, #152"
        ),
    },
    {
        "title": "[Simulation] DB 고정 패널 조회(§3.6) + NICE 45류 시드 마이그레이션",
        "labels": ["agent-simulation"],
        "body": (
            "고정 패널을 DB에서 조회하고 카테고리 시드를 정비.\n\n"
            "- DB 기반 고정 패널 조회(§3.6) — panels/personas 읽기 경로 배선\n"
            "- 고정 패널이 요청 표본 수를 무시하던 문제 수정\n"
            "- categories/kinds/category_kinds 테이블 + NICE 45류 시드(Alembic)\n\n"
            "연결 PR: #146"
        ),
    },
    {
        "title": "[Simulation] SSR 점수화 재배선(구매의도·신뢰도 임베딩 분포, opt-in)",
        "labels": ["agent-simulation"],
        "body": (
            "SSR 임베딩 기반 점수화를 구매의도·신뢰도 축에 재배선.\n\n"
            "- SSR 점수화 재배선(구매의도·신뢰도 임베딩 분포, opt-in)\n"
            "- 구매의도 분포 카드에 SSR 확률분포 표시 지원\n\n"
            "연결 PR: #152"
        ),
    },
    {
        "title": "[Simulation] 반응 엔진 Gemini 2.5 Flash 복귀 + KOBACO 벤치마크 실데이터 전환",
        "labels": ["agent-simulation"],
        "body": (
            "반응 엔진 모델과 벤치마크 데이터를 확정.\n\n"
            "- 시뮬레이션 반응 엔진을 Gemini 2.5 Flash로 복귀\n"
            "- KOBACO 벤치마크 실데이터 전환 + MDIS 데이터 현황 문서 정합\n\n"
            "연결 PR: #152"
        ),
    },
    {
        "title": "[Simulation] 실행상태 조회 API + 모델 분리 설정 + 프론트 재구독",
        "labels": ["agent-simulation"],
        "body": (
            "시뮬 실행 상태를 조회·재구독할 수 있게 배선.\n\n"
            "- 시뮬레이션 실행상태 조회 API + 모델 분리 설정\n"
            "- 프론트 재구독 반영\n\n"
            "연결 PR: #158"
        ),
    },
    {
        "title": "[Simulation] 결과 화면 재설계(탭 분리형·블루 모노크롬·페르소나 카드 그리드)",
        "labels": ["agent-simulation"],
        "body": (
            "시뮬 결과 화면을 탭 분리형으로 재설계.\n\n"
            "- 결과 히어로 재구성(목표달성+KPI 한 줄) + 개요/반응/토론/리포트 탭\n"
            "- 페르소나 반응 카드 그리드(필터·정렬) + 상세 가독화(JSON 제거·한글 라벨)\n"
            "- 시뮬레이션 내역 행 클릭 시 결과 화면으로 이동\n\n"
            "연결 PR: #162"
        ),
    },
    {
        "title": "[Simulation] 실행 히스토리 테이블(롱텀 BM25 색인) + 광고생성→시뮬 연계",
        "labels": ["agent-simulation"],
        "body": (
            "실행 이력을 적재하고 생성-시뮬을 연결.\n\n"
            "- 실행 히스토리 테이블·마이그레이션(롱텀메모리 BM25 색인)\n"
            "- 광고 생성 완료 후 시뮬레이션 연계(버튼+채팅 제안) + 광고 이미지 필수화\n\n"
            "연결 PR: #144, #151"
        ),
    },
    {
        "title": "[Simulation] 관심층 조건부 클릭 의향률(agg-3) + 세그먼트 최소표본",
        "labels": ["agent-simulation"],
        "body": (
            "관심층 조건부로 클릭 의향률을 집계.\n\n"
            "- 관심층 조건부 클릭 의향률(agg-3)\n"
            "- 세그먼트 최소표본 + PDF 개선\n\n"
            "연결 PR: #179"
        ),
    },
    {
        "title": "[Simulation] PDF 리포트 위계 정리·CDN 의존 제거 + 개선루프 KPI 조기종료",
        "labels": ["agent-simulation"],
        "body": (
            "PDF 리포트 품질·안정성 개선(기존 #123 보강).\n\n"
            "- PDF 리포트 위계 정리(KPI 색신호·단위·종합점수 근거)\n"
            "- PDF 렌더 CDN 의존 제거(폰트·Tailwind 인라인 하드닝) + 팔레트 조정\n"
            "- 세그먼트 정렬 인원 많은 순 통일(화면·PDF 불일치 해소)\n\n"
            "연결 PR: #164"
        ),
    },
    # ── 매니지먼트 (agent-management) ──
    {
        "title": "[Management] admin org 스코프(impersonation + X-Org-Id + 전체뷰 감사)",
        "labels": ["agent-management"],
        "body": (
            "ADMIN이 조직을 대리 조회·관리하는 org 스코프 체계.\n\n"
            "- X-Org-Id 헤더 캡처 ContextVar + role 인지 해석기(_require_org_id)\n"
            "- impersonation 감사 seam + write 엔드포인트 치환, 대리 연결 차단\n"
            "- _scope_org_or_all + 전 org 조회 access log + admin org 선택 드롭다운\n\n"
            "연결 PR: #132"
        ),
    },
    {
        "title": "[Management] 이상감지 선제 제안(remediation advisor) + 채팅 consult_anomaly + 알림 sink",
        "labels": ["agent-management"],
        "body": (
            "이상 감지 시 조치 옵션을 선제 제안하는 어드바이저.\n\n"
            "- remediation advisor — 실측 재검증·옵션 풀·결정론 문구(LLM 폴백)\n"
            "- 채팅 consult_anomaly 도구(이상 재검증·조치 옵션 보조 진입, 위임만)\n"
            "- 채팅 알림 sink(판정표 스팸 방지·race 잠금) + 수동 스캔 엔드포인트\n\n"
            "연결 PR: #150"
        ),
    },
    {
        "title": "[Management] 챗 인라인 REPLACE_CREATIVE 소재 교체 카드(picker·승인·집행)",
        "labels": ["agent-management"],
        "body": (
            "채팅에서 소재 교체를 인라인 카드로 처리.\n\n"
            "- 챗 replace_creative tool — 소재 교체 후보 picker 위젯\n"
            "- ChatReplaceCreativeCard — 후보 선택·프리뷰·승인·집행 챗 카드\n"
            "- 소재 교체 시 기존 광고 도착지(랜딩) 보존\n\n"
            "연결 PR: #160"
        ),
    },
    {
        "title": "[Management] 집행 게이트 하드닝 + 승인 원장(management_approval_records·Alembic 0010)",
        "labels": ["agent-management"],
        "body": (
            "집행 승인을 원장으로 기록·강제하는 게이트 하드닝.\n\n"
            "- 승인 원장 테이블(management_approval_records) + Alembic 0010\n"
            "- 승인 발행+원장 기록 issue_approval — 검증 강제 발행 단일 진입점\n"
            "- 승인 원장 게이트 배선(/approve 인증·발행 4곳 일원화) + GET /exec-gate\n\n"
            "연결 PR: #166"
        ),
    },
    {
        "title": "[Management] RAG 검색 다양화·거부율 KB + 신뢰도 골든셋·러너·리포트",
        "labels": ["agent-management"],
        "body": (
            "매니지먼트 RAG 품질·신뢰도 측정 체계.\n\n"
            "- RAG 검색 다양화·프롬프트 라우팅·거부율 KB 반영\n"
            "- 신뢰도(faithfulness) 골든셋·러너·리포트 + 프론트\n\n"
            "연결 PR: #163"
        ),
    },
    {
        "title": "[Management] 채팅 전체리포트·전체지표·기간예산 라우팅",
        "labels": ["agent-management"],
        "body": (
            "매니지먼트 채팅의 조회 범위·라우팅 확장.\n\n"
            "- 매니지먼트 채팅 전체리포트·전체지표·기간예산 + 라우팅 프롬프트 보강\n"
            "- 조치 실행 성공 시 캠페인 미해결 알림 자동 해소\n"
            "- 시뮬 외부 이미지 URL S3 선영속(Meta 소재 403 해소)\n\n"
            "연결 PR: #170, #157"
        ),
    },
    # ── 인프라 / 인증 / 배포 (devops·setup) ──
    {
        "title": "[Infra] EC2 프로비저닝 자동화 심화(EIP·자동 .env·Portainer·resize·TLS) + Secrets 10→6",
        "labels": ["devops"],
        "body": (
            "배포 인프라 프로비저닝을 자동화.\n\n"
            "- Elastic IP 고정·backend/.env 자동 scp·Portainer 관리자 자동 생성\n"
            "- TLS 인증서·ECR 정리·PEM 팀 공유 + resize_instance.py(타입 전환)\n"
            "- 비밀 아닌 값 평문화로 GitHub Secrets 최소화(10→6)\n\n"
            "연결 PR: #148"
        ),
    },
    {
        "title": "[Infra] CI/CD 단일 워크플로우 통합(test 게이트)",
        "labels": ["devops"],
        "body": (
            "CI와 CD를 단일 워크플로우로 통합하고 test 게이트 적용.\n\n"
            "- CI/CD를 단일 워크플로우로 통합(test 게이트)\n"
            "- CI/CD push·PR 트리거 브랜치 정리\n\n"
            "연결 PR: #154"
        ),
    },
    {
        "title": "[Infra] ADMIN 조직·회원 복원/영구삭제 + org_status 필터 + 관리 화면 개편",
        "labels": ["backend", "frontend"],
        "body": (
            "ADMIN의 조직·회원 관리 기능 확장.\n\n"
            "- ADMIN 조직·회원 복원/영구삭제 API + 목록 페이지네이션·org_status\n"
            "- ADMIN 내역 조직 상태 필터·컬럼 + 관리 화면 개편\n"
            "- 조직/회원 관리 분리\n\n"
            "연결 PR: #154, #183"
        ),
    },
    {
        "title": "[Infra] Meta 심사용 정책 페이지 3종(개인정보·약관·데이터삭제)",
        "labels": ["frontend"],
        "body": (
            "Meta 앱 심사에 필수인 정책 페이지 복구.\n\n"
            "- 정책 페이지 3종 — 개인정보처리방침·이용약관·데이터삭제 안내\n\n"
            "연결 PR: #154"
        ),
    },
    # ── 프론트 개편 (frontend) ──
    {
        "title": "[Frontend] 디자인시스템 전면 개편 — shadcn+토큰+테마 14종+앱셸 리스킨+랜딩 재설계",
        "labels": ["frontend"],
        "body": (
            "프론트 전반을 디자인 토큰 기반으로 재개편.\n\n"
            "- shadcn 도입 + 디자인 토큰 체계 + 테마 14종 + /themes 갤러리\n"
            "- 앱 셸 전면 리스킨(사이드바·레이아웃·패널 토큰화 + lucide)\n"
            "- 랜딩 Apple식 다이나믹 진입 재설계(framer-motion) + Pretendard 폰트\n\n"
            "연결 PR: #169, #164"
        ),
    },
    {
        "title": "[Frontend] 역할별 대시보드 재구성(KPI 델타·주간추이·활동피드·크레딧) + 요약 엔드포인트",
        "labels": ["frontend"],
        "body": (
            "역할별로 대시보드를 실데이터 기반 재구성.\n\n"
            "- 대시보드 요약 엔드포인트 — KPI 델타·주간추이·클릭의향률(append-only)\n"
            "- 역할별 대시보드 재구성(KPI 델타·주간추이 차트·활동피드·크레딧)\n"
            "- 크레딧 위젯 역할 인지형(USER 읽기전용) + 관리자 대시보드 실데이터\n\n"
            "연결 PR: #169"
        ),
    },
    # ── 정리성 (chore) ──
    {
        "title": "[Chore] SQS 설정·CI env 제거(인프로세스 async 정본화)",
        "labels": ["chore", "devops"],
        "body": (
            "미사용 SQS 흔적을 제거하고 인프로세스 async로 정본화한 이력.\n\n"
            "- 미사용 SQS 설정·CI env 제거 + 정본 문서 인프로세스 async로 갱신\n"
            "- 시뮬 비용 문서 통합 + SQS 서술 제거\n\n"
            "연결 PR: #134, #158"
        ),
    },
    {
        "title": "[Chore] SSR 점수화 기본값 토글 전환·revert 왕복 정리",
        "labels": ["chore", "agent-simulation"],
        "body": (
            "SSR 점수화 기본 활성/비활성 전환을 여러 번 오간 이력.\n\n"
            "- SSR 점수화 기본 활성화로 변경 → llm으로 revert → 기본 ON 재확정\n"
            "- 최종 상태와 테스트 정합 정리\n\n"
            "연결 PR: #168, #171, #179"
        ),
    },
]


def get_token() -> str:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token.strip()
    try:
        out = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        sys.exit("토큰을 찾을 수 없습니다. GITHUB_TOKEN 설정 또는 `gh auth login` 후 재시도하세요.")


def fetch_existing_titles(client: httpx.Client) -> set[str]:
    titles: set[str] = set()
    page = 1
    while True:
        resp = client.get(
            f"{API}/repos/{REPO}/issues",
            params={"state": "all", "per_page": 100, "page": page},
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        # PR도 issues 엔드포인트에 섞여 나오므로 pull_request 키가 있으면 제외.
        titles.update(i["title"] for i in batch if "pull_request" not in i)
        page += 1
    return titles


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    with httpx.Client(headers=headers, timeout=30.0) as client:
        existing = fetch_existing_titles(client)

        created, skipped = 0, 0
        for issue in ISSUES:
            if issue["title"] in existing:
                print(f"[skip] 이미 존재: {issue['title']}")
                skipped += 1
                continue

            if dry_run:
                print(f"[dry-run] 생성 예정: {issue['title']}  labels={issue['labels']}")
                created += 1
                continue

            resp = client.post(
                f"{API}/repos/{REPO}/issues",
                json={
                    "title": issue["title"],
                    "body": issue["body"],
                    "labels": issue["labels"],
                },
            )
            if resp.status_code == 201:
                print(f"[ok] #{resp.json()['number']} {issue['title']}")
                created += 1
            else:
                print(f"[fail] {resp.status_code} {issue['title']} -> {resp.text}")

        verb = "생성 예정" if dry_run else "생성"
        print(f"\n완료: {created}건 {verb}, {skipped}건 건너뜀(중복).")


if __name__ == "__main__":
    main()
