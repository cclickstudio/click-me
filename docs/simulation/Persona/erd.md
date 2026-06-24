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

-- 페르소나 = 단계1~3 통계 샘플링(LLM✗) + 4-a 서사(profile_narrative만 LLM). 고정 패널(version) 단위 1회 저장·재사용(§3.6).
-- social_values_deep(체면·동조·눈치, 작업4)·weight(표본 가중)은 페르소나 테이블에 미영속 —
--   전자는 Phase2 프레임워크(값 비어 반응 무변화 — 데이터 주입 시 컬럼 추가 + Alembic), 후자는 페르소나반응.weight로 사본 저장.
CREATE TABLE `페르소나` (
	`ID`	UUID	NULL,
	`panel_id`	UUID	NOT NULL,
	`age`	INT	NOT NULL,
	`gender`	VARCHAR(10)	NOT NULL,
	`region`	VARCHAR(50)	NOT NULL,
	`ocean`	JSONB	NOT NULL,
	`media_behavior`	JSONB	NOT NULL,
	`consumption_values`	JSONB	NOT NULL,
	`socioeconomic`	JSONB	NOT NULL,	-- 소득구간·학력(KISDI) — 구매의도·가격적합 grounding (단계1 확장)
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

-- noticed_first(§4-b salience, 프로필상 가장 먼저 주의 간 요소)는 계약(PersonaReaction)·분석 핸드오프로만
--   흐르는 탐색적 신호라 컬럼 미영속. DB 보관이 필요해지면 별도 PR + Alembic으로 추가.
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
	`brand_recognized`	BOOLEAN	NOT NULL	DEFAULT FALSE,	-- 브랜드 식별 여부(Fluency, REPORT §2-5, 마이그 010)
	`perceived_brand`	VARCHAR(200)	NULL,	-- 인식한 브랜드/제품명(선언 의도와 대조해 오귀속 분해)
	`utterance`	TEXT	NULL,
	`qa_passed`	BOOLEAN	NOT NULL,
	`qa_fail_reason`	VARCHAR(100)	NULL,
	`created_at`	TIMESTAMP	NOT NULL
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
	`structured_analysis`	JSONB	NOT NULL,	-- 훅·카피·CTA + visual_elements(§4-a 시각 인벤토리)·brand_era(Tier 2 브랜드 시대성) 포함
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
	`brand_recognition_rate`	DECIMAL(5,4)	NOT NULL	DEFAULT 0,	-- QA 통과분 가중 브랜드 식별률(§2-5, 마이그 010)
	`variance_warning`	BOOLEAN	NOT NULL,
	`payload`	JSONB	NOT NULL,
	`engine_version`	VARCHAR(50)	NOT NULL,
	`created_at`	TIMESTAMP	NOT NULL
);

