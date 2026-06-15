import base64

import aioboto3
from langsmith import traceable
from openai import AsyncOpenAI

from core.config import settings
from domain.generator.contracts.schemas import ProductAnalysis
from tools.utils import safe_json_loads, str_list, str_or_none

_client = AsyncOpenAI(timeout=60.0)

_PROMPT = """\
이 광고 이미지를 분석하고 아래 JSON 형식으로만 응답하세요.

{
  "product_name": "광고에서 추출한 제품 또는 브랜드명",
  "core_values": ["핵심 가치 1", "핵심 가치 2"],
  "pain_points": ["타겟이 겪는 문제 1", "문제 2"],
  "benefits": ["제품 혜택 1", "혜택 2"],
  "target_audience": "추정 타겟 고객층 (나이, 성별, 관심사 등)",
  "objective": "광고 목적 (awareness | conversion | promotion | lead_gen 중 하나)"
}

이미지에서 명확히 알 수 없는 항목은 광고 분위기와 비주얼 단서로 합리적으로 추론하세요."""


async def _download_from_s3(s3_key: str) -> bytes:
    session = aioboto3.Session(
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )
    async with session.client("s3") as s3:
        response = await s3.get_object(Bucket=settings.s3_bucket_name, Key=s3_key)
        return await response["Body"].read()


@traceable(name="AdInfoExtractor", metadata={"pipeline": "generator"})
async def extract_ad_info(
    s3_key: str,
    product_name: str | None = None,
    description: str | None = None,
    target: str | None = None,
    objective: str | None = None,
) -> tuple[bytes, ProductAnalysis]:
    """S3에서 원본 광고 이미지를 다운로드하고 Vision으로 제품 정보를 역추출한다.

    사용자가 입력한 값이 있으면 Vision 추출 결과를 덮어쓴다.
    반환: (원본 이미지 bytes, ProductAnalysis)
    """
    image_bytes = await _download_from_s3(s3_key)
    b64 = base64.b64encode(image_bytes).decode()

    response = await _client.chat.completions.create(
        model="gpt-4o",
        max_tokens=400,
        temperature=0.1,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64}",
                            "detail": "low",
                        },
                    },
                    {"type": "text", "text": _PROMPT},
                ],
            }
        ],
        response_format={"type": "json_object"},
    )

    raw = safe_json_loads(response.choices[0].message.content, fallback="{}")

    # 사용자 입력값이 있으면 Vision 추출값보다 우선 적용
    extracted_product_name = (
        product_name or str_or_none(raw.get("product_name")) or "알 수 없는 제품"
    )

    # description이 있으면 benefits/core_values 보강에 사용
    extracted_benefits = str_list(raw.get("benefits"))
    if description and not extracted_benefits:
        extracted_benefits = [description]

    return image_bytes, ProductAnalysis(
        product_name=extracted_product_name,
        core_values=str_list(raw.get("core_values")) or [extracted_product_name],
        pain_points=str_list(raw.get("pain_points")),
        benefits=extracted_benefits,
        target_audience=target or str_or_none(raw.get("target_audience")) or "일반 소비자",
        objective=objective or str_or_none(raw.get("objective")) or "conversion",
    )
