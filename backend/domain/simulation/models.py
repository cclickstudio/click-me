# 시뮬레이터 소유 ORM 엔티티 — 추후 다른 도메인 ERD 확정 시 core/models.py로 병합
#
# 현재는 도메인 로컬 DeclarativeBase로 격리해 core 메타데이터 오염을 피한다.
# projects / ads 는 core/models.py 소유이므로 여기서 재정의하지 않고 UUID FK로만 참조.