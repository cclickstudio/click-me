"""Generator DTO — graph 파이프라인 요청/산출물 스키마.

생성·개선을 모두 graph(LangGraph) 파이프라인으로 처리한다.
파이프라인 내부 산출물(ProductAnalysis/StrategyOutput/AdCopy 등)은 pipeline_schemas.py 참조.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from domain.generator.contracts.enums import GenerationMode


class GenerationCreateRequest(BaseModel):
    """생성/개선 통합 입력 — mode로 분기.

    - create: product_name / product_description / target_audience 필수
    - improve: existing_ad_s3_key / simulation_summary 필수
    """

    mode: GenerationMode = GenerationMode.CREATE
    project_id: str | None = None
    format: str = "single"  # single | carousel(카드뉴스 5장)

    # 생성모드 입력
    product_name: str = ""
    product_description: str = ""
    target_audience: str = ""
    campaign_objective: str = "conversion"

    # 개선모드 입력
    existing_ad_s3_key: str | None = None  # 참고용 — bytes 로드 없이 텍스트 힌트로만 사용
    simulation_summary: str | None = None  # 시뮬 결과 요약(KPI 등)
    improvement_direction: str | None = None  # 토론 개선 권고("그래서 무엇을 고치면 되나")
    fix_requests: str | None = None  # 사용자 수정 요청(개선방향 1순위)
    plain_summary: str | None = None  # 시뮬 AI 분석 텍스트 (개선 모드 UI "AI 분석" 섹션용)
    product_cutout_s3_key: str | None = None  # 생성 모드에서 저장된 누끼 이미지 S3 키

    # 공통 — 브랜드 / 출력
    brand_color: str | None = None  # hex (#RRGGBB)
    brand_logo_url: str | None = None  # deprecated — 직접 URL 입력 (구형 호환용)
    brand_logo_s3_key: str | None = None  # S3 업로드 후 키 (brand_profile 캐시 연동)
    tone_and_manner: str | None = None
    # 생성 모드 전용 — 상품 이미지 기반 생성 (추후 S3 키 방식으로 전환 예정)
    product_image_temp_key: str | None = None  # 테스트용 서버 메모리 임시 키
    width: int = Field(default=1080, ge=256, le=4096)
    height: int = Field(default=1080, ge=256, le=4096)

    @model_validator(mode="after")
    def _check_required_by_mode(self) -> GenerationCreateRequest:
        if self.mode == GenerationMode.IMPROVE:
            if not (self.simulation_summary or "").strip():
                raise ValueError("개선모드에는 simulation_summary가 필요합니다.")
        else:
            missing = [
                name
                for name, value in (
                    ("product_name", self.product_name),
                    ("product_description", self.product_description),
                    ("target_audience", self.target_audience),
                )
                if not (value or "").strip()
            ]
            if missing:
                raise ValueError(f"생성모드 필수 필드 누락: {', '.join(missing)}")
        return self


class CandidateExplanation(BaseModel):
    """생성 이유 설명 (계획서 8장)."""

    applied_target: str
    applied_strategy: str
    applied_template: str
    rationale: str
