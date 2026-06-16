CREATE TABLE `광고` (
	`ID`	UUID	NULL,
	`project_id`	UUID	NOT NULL,
	`title`	VARCHAR(255)	NOT NULL,
	`media_type`	VARCHAR(20)	NOT NULL,
	`asset_url`	VARCHAR(500)	NULL,
	`copy_text`	TEXT	NULL,
	`industry_category`	VARCHAR(100)	NOT NULL,
	`product_category`	VARCHAR(100)	NOT NULL,
	`ad_objective`	VARCHAR(50)	NOT NULL,
	`target_filter`	JSONB	NULL,
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

CREATE TABLE `루브릭점수` (
	`ID`	UUID	NULL,
	`ad_analysis_id`	UUID	NOT NULL,
	`dimension`	VARCHAR(50)	NOT NULL,
	`score`	INT	NOT NULL,
	`evidence`	JSONB	NOT NULL,
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

CREATE TABLE `광고해석` (
	`ID`	UUID	NULL,
	`ad_id`	UUID	NOT NULL,
	`structured_analysis`	JSONB	NOT NULL,
	`detected_industry`	VARCHAR(100)	NULL,
	`detected_target`	VARCHAR(100)	NULL,
	`detected_message`	TEXT	NULL,
	`intent_mismatch`	BOOLEAN	NOT NULL,
	`mismatch_detail`	JSONB	NULL,
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

