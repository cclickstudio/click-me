# 컴포즈 모드 단독 테스트 스크립트 — uv run python test_compose.py <이미지경로>
import asyncio
import sys
import time
from pathlib import Path


async def main() -> None:
    image_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("sample_product.png")
    if not image_path.exists():
        print(f"이미지 파일 없음: {image_path}")
        print("사용법: uv run python test_compose.py <상품이미지.png>")
        sys.exit(1)

    from domain.generator.contracts.enums import AdSize, AdStrategy, TemplateType
    from domain.generator.contracts.pipeline_schemas import ProductAnalysis
    from domain.generator.pipeline.image_generator import generate_image, remove_product_background

    product_image = image_path.read_bytes()

    print(f"[1/3] 배경 제거 중... ({image_path.name})")
    t0 = time.perf_counter()
    cutout = await remove_product_background(product_image)
    t1 = time.perf_counter()
    print(f"      완료: {t1 - t0:.1f}s  누끼 크기={len(cutout):,} bytes")

    product_analysis = ProductAnalysis(
        product_name="테스트 상품",
        core_values=["신뢰", "품질"],
        pain_points=[],
        benefits=["편리함", "효율성"],
        target_audience="20-30대",
        objective="구매 전환",
    )

    results: list[tuple[str, str]] = []
    for template in (TemplateType.A, TemplateType.B, TemplateType.C):
        label = f"템플릿 {template.value}"
        print(f"[2/3] {label} 컴포즈 생성 중...")
        t2 = time.perf_counter()
        result = await generate_image(
            product_analysis=product_analysis,
            strategy=AdStrategy.BENEFIT,
            template=template,
            size=AdSize.SQUARE,
            product_cutout_bytes=cutout,
        )
        t3 = time.perf_counter()
        out_path = f"output_compose_{template.value}.png"
        Path(out_path).write_bytes(result)
        results.append((label, out_path))
        print(f"      완료: {t3 - t2:.1f}s  → {out_path}")

    print("\n[3/3] 결과 요약")
    print(f"      누끼 제거: {t1 - t0:.1f}s")
    for label, path in results:
        print(f"      {label}: {path}")
    print("\nLangSmith에서 토큰·비용·시간 확인: image-model:remove-bg + image-model:gemini-compose")


asyncio.run(main())
