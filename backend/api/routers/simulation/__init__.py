# 시뮬레이션 라우터 패키지 — main.py 등록: app.include_router(router, prefix="/api/simulation")
from api.routers.simulation.router import router

__all__ = ["router"]
