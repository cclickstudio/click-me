-- 광고 = 사용자 선언 의도(시뮬레이터 탭 입력)의 원천. 광고해석의 교차검증 기준값.
-- 프론트 입력 매핑: 광고 소재→media_type/asset_url/copy_text · 광고 제목→title
--   · 광고 설명→description · 제품 카테고리→product_category · 캠페인 목표→ad_objective
--   · 상품·서비스 분류(NICE 1~45류)→service_class · 타깃(성별·연령)→target_filter
CREATE TABLE `광고` (
	`ID`	UUID	NULL,
	`project_id`	UUID	NOT NULL,
	`title`	VARCHAR(255)	NOT NULL,	-- 광고 제목(필수)
	`media_type`	VARCHAR(20)	NOT NULL,	-- image / text
	`asset_url`	VARCHAR(500)	NULL,	-- 이미지 모드 소재 URL
	`copy_text`	TEXT	NULL,	-- 텍스트 모드 카피(헤드라인/본문/CTA)
	`description`	TEXT	NULL,	-- 광고 설명(선택) — 해석 보조 입력
	`industry_category`	VARCHAR(100)	NOT NULL,	-- 업종
	`product_category`	VARCHAR(100)	NOT NULL,	-- 제품 카테고리(상표분류군명)
	`service_class`	INT	NULL,	-- 상품·서비스 분류(NICE 1~45류, 선택) — 벤치마크 매칭 보조
	`ad_objective`	VARCHAR(50)	NOT NULL,	-- 캠페인 목표
	`target_filter`	JSONB	NULL,	-- 선언 타깃(성별·연령)
	`status`	VARCHAR(20)	NOT NULL	DEFAULT 'DRAFT',
	`created_by`	UUID	NOT NULL,
	`created_at`	TIMESTAMP	NOT NULL,
	`updated_at`	TIMESTAMP	NOT NULL
);

CREATE TABLE `페르소나` (
	`ID`	UUID	NULL,
	`panel_id`	UUID	NOT NULL,
	`age`	INT	NOT NULL,
	`gender`	VARCHAR(10)	NOT NULL,
	`region`	VARCHAR(50)	NOT NULL,
	`ocean`	JSONB	NOT NULL,
	`media_behavior`	JSONB	NOT NULL,
	`consumption_values`	JSONB	NOT NULL,
	`profile_narrative`	TEXT	NOT NULL,
	`created_at`	TIMESTAMP	NOT NULL
);

CREATE TABLE `시뮬레이션` (
	`ID`	UUID	NULL,
	`ad_id`	UUID	NOT NULL,
	`ad_analysis_id`	UUID	NOT NULL,
	`panel_id`	UUID	NOT NULL,
	`organization_id`	UUID	NOT NULL,
	`target_filter`	JSONB	NULL,
	`target_mode`	VARCHAR(10)	NOT NULL	DEFAULT 'AUTO',
	`sample_size`	INT	NOT NULL,
	`qa_passed_count`	INT	NULL,
	`low_sample_warning`	BOOLEAN	NOT NULL,
	`status`	VARCHAR(20)	NOT NULL	DEFAULT 'QUEUED',
	`model_version`	VARCHAR(50)	NOT NULL,
	`error_detail`	JSONB	NULL,
	`created_by`	UUID	NOT NULL,
	`started_at`	TIMESTAMP	NULL,
	`completed_at`	TIMESTAMP	NULL,
	`created_at`	TIMESTAMP	NOT NULL
);

CREATE TABLE `토론세션` (
	`ID`	UUID	NULL,
	`시뮬레이션ID`	UUID	NOT NULL,
	`상태`	VARCHAR(20)	NOT NULL	DEFAULT 'PENDING',
	`MS결석여부`	BOOLEAN	NOT NULL,
	`LLM콜수`	INT	NULL,
	`모델버전`	VARCHAR(50)	NOT NULL,
	`생성일시`	TIMESTAMP	NOT NULL
);

CREATE TABLE `조직멤버` (
	`ID`	UUID	NULL,
	`organization_id`	UUID	NOT NULL,
	`user_id`	UUID	NOT NULL,
	`role`	VARCHAR(20)	NOT NULL,
	`invited_by`	UUID	NULL,
	`status`	VARCHAR(20)	NOT NULL	DEFAULT 'PENDING',
	`joined_at`	TIMESTAMP	NULL,
	`created_at`	TIMESTAMP	NOT NULL
);

CREATE TABLE `보고서` (
	`ID`	UUID	NULL,
	`시뮬레이션ID`	UUID	NOT NULL,
	`양식버전`	VARCHAR(20)	NOT NULL,
	`패널버전`	VARCHAR(20)	NOT NULL,
	`모델버전`	VARCHAR(50)	NOT NULL,
	`보고서데이터`	JSONB	NOT NULL,
	`파일경로`	VARCHAR(500)	NULL,
	`생성일시`	TIMESTAMP	NOT NULL
);

CREATE TABLE `페르소나반응` (
	`ID`	UUID	NULL,
	`simulation_id`	UUID	NOT NULL,
	`persona_id`	UUID	NOT NULL,
	`exposure_context`	VARCHAR(50)	NULL,
	`aisas`	JSONB	NOT NULL,
	`drop_stage`	VARCHAR(20)	NULL,
	`drop_reason_tag`	VARCHAR(50)	NULL,
	`purchase_intent`	INT	NOT NULL,
	`trust`	INT	NOT NULL,
	`rejected`	BOOLEAN	NOT NULL,
	`rejection_reason_tag`	VARCHAR(50)	NULL,
	`emotion_tag`	VARCHAR(50)	NOT NULL,
	`perceived_message`	TEXT	NULL,
	`perceived_target`	VARCHAR(100)	NULL,
	`utterance`	TEXT	NULL,
	`qa_passed`	BOOLEAN	NOT NULL,
	`qa_fail_reason`	VARCHAR(100)	NULL,
	`created_at`	TIMESTAMP	NOT NULL
);

CREATE TABLE `토론발언` (
	`ID`	UUID	NULL,
	`세션ID`	UUID	NOT NULL,
	`에이전트`	VARCHAR(10)	NOT NULL,
	`라운드`	INT	NOT NULL,
	`주장`	TEXT	NOT NULL,
	`반박대상발언ID`	UUID	NULL,
	`인용근거`	JSONB	NOT NULL,
	`판정`	VARCHAR(30)	NULL,
	`생성일시`	TIMESTAMP	NOT NULL
);

CREATE TABLE `패널` (
	`ID`	UUID	NULL,
	`version`	VARCHAR(20)	NOT NULL,
	`size`	INT	NOT NULL,
	`seed`	VARCHAR(50)	NOT NULL,
	`model_version`	VARCHAR(50)	NOT NULL,
	`grounding_meta`	JSONB	NOT NULL,
	`status`	VARCHAR(20)	NOT NULL	DEFAULT 'BUILDING',
	`built_at`	TIMESTAMP	NULL,
	`created_at`	TIMESTAMP	NOT NULL
);

-- 루브릭점수 = 의도 정합 점수(선언 입력 ↔ VLM 감지 의도 일치도). '광고 솜씨 절대평가' 아님.
-- 광고해석의 교차검증 콜 1회에서 mismatch_detail(정성)과 함께 산출되는 정량 투영. 같은 비교의 두 표현.
-- dimension ∈ {category_alignment, objective_alignment, message_alignment} (선언 입력 있는 차원만).
-- score 0~100 = 해당 차원 정합도. intent_mismatch는 임계(예 60) 미만 차원 존재 시 true로 광고해석에 기록.
CREATE TABLE `루브릭점수` (
	`ID`	UUID	NULL,
	`ad_analysis_id`	UUID	NOT NULL,	-- 광고해석 FK
	`dimension`	VARCHAR(50)	NOT NULL,	-- category_alignment / objective_alignment / message_alignment
	`score`	INT	NOT NULL,	-- 0~100 정합도
	`evidence`	JSONB	NOT NULL,	-- {declared, detected, note} — 비교 근거
	`created_at`	TIMESTAMP	NOT NULL
);

CREATE TABLE `프로젝트` (
	`ID`	UUID	NULL,
	`organization_id`	UUID	NOT NULL,
	`name`	VARCHAR(255)	NOT NULL,
	`description`	TEXT	NULL,
	`status`	VARCHAR(20)	NOT NULL	DEFAULT 'ACTIVE',
	`created_by`	UUID	NOT NULL,
	`created_at`	TIMESTAMP	NOT NULL,
	`updated_at`	TIMESTAMP	NOT NULL
);

CREATE TABLE `사용자` (
	`ID`	UUID	NULL,
	`email`	VARCHAR(255)	NOT NULL,
	`password_hash`	VARCHAR(255)	NOT NULL,
	`name`	VARCHAR(100)	NOT NULL,
	`role`	VARCHAR(20)	NOT NULL,
	`status`	VARCHAR(20)	NOT NULL	DEFAULT 'ACTIVE',
	`created_by`	UUID	NULL,
	`last_login_at`	TIMESTAMP	NULL,
	`created_at`	TIMESTAMP	NOT NULL,
	`updated_at`	TIMESTAMP	NOT NULL
);

CREATE TABLE `조직` (
	`ID`	UUID	NULL,
	`name`	VARCHAR(255)	NOT NULL,
	`slug`	VARCHAR(100)	NOT NULL,
	`status`	VARCHAR(20)	NOT NULL	DEFAULT 'ACTIVE',
	`created_at`	TIMESTAMP	NOT NULL,
	`updated_at`	TIMESTAMP	NOT NULL
);

-- 광고해석 = VLM이 감지한 값(detected_*) + 선언 입력(광고 테이블) 대조 결과.
-- 선언값은 광고 테이블이 원천이라 여기 중복 저장하지 않는다. intent_mismatch/mismatch_detail만 보관.
-- mismatch_detail(JSONB) = 차원별 {declared, detected, match(bool), note}. 차원: category·objective·message (ANALYSIS §3.5-3).
-- 타깃은 선언 입력이 아니므로(샘플링용 target_filter) 교차검증 차원 제외. detected_target은 VLM 기술 정보로만 기록.
CREATE TABLE `광고해석` (
	`ID`	UUID	NULL,
	`ad_id`	UUID	NOT NULL,	-- 광고(선언 입력) 참조
	`structured_analysis`	JSONB	NOT NULL,	-- 훅·카피·CTA·비주얼 구조화
	`detected_industry`	VARCHAR(100)	NULL,	-- 감지 업종 ↔ 제품 카테고리(category 차원)
	`detected_objective`	VARCHAR(50)	NULL,	-- 감지 캠페인 목표 ↔ ad_objective(objective 차원, 신규)
	`detected_message`	TEXT	NULL,	-- 감지 핵심 메시지 ↔ 광고 제목(message 차원)
	`detected_target`	VARCHAR(100)	NULL,	-- 감지 타깃 — 기술 정보(선언 타깃 없어 미스매치 비대상)
	`intent_mismatch`	BOOLEAN	NOT NULL,	-- 비교된 차원 중 하나라도 불일치면 true
	`mismatch_detail`	JSONB	NULL,	-- 차원별 declared vs detected 스냅샷(선언 입력 있는 차원만)
	`model_version`	VARCHAR(50)	NOT NULL,
	`created_at`	TIMESTAMP	NOT NULL
);

CREATE TABLE `시뮬레이션집계` (
	`ID`	UUID	NULL,
	`simulation_id`	UUID	NOT NULL,
	`click_intent_rate`	DECIMAL(5,4)	NOT NULL,
	`ci_low`	DECIMAL(5,4)	NOT NULL,
	`ci_high`	DECIMAL(5,4)	NOT NULL,
	`purchase_intent`	DECIMAL(3,2)	NOT NULL,
	`trust_avg`	DECIMAL(3,2)	NOT NULL,
	`rejection_rate`	DECIMAL(5,4)	NOT NULL,
	`variance_warning`	BOOLEAN	NOT NULL,
	`payload`	JSONB	NOT NULL,
	`engine_version`	VARCHAR(50)	NOT NULL,
	`created_at`	TIMESTAMP	NOT NULL
);

CREATE TABLE `진단` (
	`ID`	UUID	NULL,
	`시뮬레이션ID`	UUID	NOT NULL,
	`진단차원`	VARCHAR(50)	NOT NULL,
	`루브릭점수`	INT	NOT NULL,
	`벤치마크키`	VARCHAR(100)	NULL,
	`진단문장`	TEXT	NOT NULL,
	`합의유형`	VARCHAR(20)	NOT NULL,
	`이견블록`	JSONB	NULL,
	`인용근거`	JSONB	NOT NULL,
	`생성일시`	TIMESTAMP	NOT NULL
);

CREATE TABLE `개선권고` (
	`ID`	UUID	NULL,
	`시뮬레이션ID`	UUID	NOT NULL,
	`진단ID`	UUID	NOT NULL,
	`진단차원`	VARCHAR(50)	NOT NULL,
	`권고등급`	VARCHAR(20)	NOT NULL,
	`우선순위`	INT	NOT NULL,
	`권고문장`	TEXT	NOT NULL,
	`진단근거`	JSONB	NOT NULL,
	`처방근거`	JSONB	NULL,
	`생성일시`	TIMESTAMP	NOT NULL
);

