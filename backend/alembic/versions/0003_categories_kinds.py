# categories/kinds/category_kinds 마스터 테이블 생성 + NICE 45류 시드 데이터 주입.
"""add categories/kinds/category_kinds tables + NICE 45류 seed data

Revision ID: 0003_categories_kinds
Revises: 0002_persona_weight
Create Date: 2026-07-03

ORM 미관리 읽기전용 참조 테이블(domain/simulation/adapters/category_repo.py 참고,
core/models.py 의도적 미선언) — raw DDL로 직접 관리. 스키마는 docs/db-schema.md에
이미 문서화돼 있었으나, 실 데이터(45류 설명·대분류 그룹핑)는 git에 커밋된 적이 없어
(daf52d8이 조회 API만 추가) 팀 확인 후 이 마이그레이션에서 재구성해 명문화한다.
전부 멱등(테이블·행 존재 시 스킵) — 이미 채워진 DB에 재실행해도 안전.
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_categories_kinds"
down_revision = "0002_persona_weight"
branch_labels = None
depends_on = None

_KINDS: dict[int, str] = {
    1: "화학제품, 비료, 코팅제, 비닐",
    2: "페인트, 니스, 래커, 잉크, 염료",
    3: "화장품, 향수, 디퓨져, 비누, 세면용품, 세탁세제",
    4: "양초, 향초, 램프",
    5: "의약제, 살균제, 제초제",
    6: "금속재료, 건축재료",
    7: "기계 및 공작기계, 모터 및 엔진, 농기구, 자동판매기",
    8: "수공구, 수동기구, 칼",
    9: "컴퓨터, 소프트웨어, CD, DVD, USB, 핸드폰 악세서리, 카메라",
    10: "의료용 기계기구, 의료재료",
    11: "조명장치, 조리장치, 냉난방장치",
    12: "자동차, 비행기, 선박, 수송기계기구",
    13: "총포탄, 화약류, 불꽃",
    14: "귀금속, 보석류, 시계",
    15: "악기",
    16: "서적, 인쇄물, 잡지, 사진, 문방구, 미술재료, 교육재료",
    17: "고무, 플라스틱 제품, 충전·방음·단열·절연재료",
    18: "가죽, 인조가죽 제품, 트렁크 및 여행용 가방, 우산, 양산",
    19: "비금속제 건축재료, 비금속제 이동식 건축물, 비금속제 기념물",
    20: "가구, 쿠션, 액자, 목재, 인테리어 장식품",
    21: "가정용품, 주방용 기구, 용기, 스펀지, 솔, 청소용구, 유리, 도자기 제품",
    22: "로프, 끈, 망, 텐트, 차양막, 타폴린, 돛, 충전용 재료",
    23: "직물용 실(絲)",
    24: "직물, 직물제품, 침대커버, 테이블커버",
    25: "의류, 신발, 모자",
    26: "레이스, 자수포, 리본, 단추, 핀, 바늘, 조화(造花)",
    27: "카펫, 매트, 리놀륨, 비직물제 벽걸이",
    28: "장난감, 게임기, 오락 및 놀이용구, 체조용품 및 운동용품",
    29: "육류, 어류, 절임, 조림, 냉동, 건조, 조리된 식품, 계란, 우유, 유제품",
    30: "커피, 차(茶), 쌀, 빵, 과자, 빙과, 소금, 소스(조미료), 향신료",
    31: "곡물, 농업·원예·임산물, 신선과일 및 채소, 종자, 식물, 사료",
    32: "맥주, 광천수, 탄산수, 음료, 과실음료 및 과실주스",
    33: "와인, 소주, 위스키, 탁주, 담금주",
    34: "담배, 흡연용품, 성냥",
    35: "통신판매업, 온라인쇼핑몰, 광고업, 각종도소매업, 컨설팅, 무역업",
    36: "보험업, 임대업, 분양업, 투자자문업, 금융업, 부동산업, 할부리스업",
    37: "건축건설업, 자동차정비업, 인테리어, 수리업, 세탁업, 청소업",
    38: "통신업, 방송업, 인터넷방송, 데이터전송업, 온라인컨텐츠 전송업",
    39: "운송업, 여행예약, 관광업, 택배업, 이사대행, 견인업, 차량임대업, 창고업",
    40: "인쇄제본업, 목공업, 제분업, 식품가공, 소재가공업",
    41: "학원, 교육, 출판, 연예, 유학알선, 피트니스, 스포츠, 게임, 공연문화활동업",
    42: "프로그래밍업, 웹·제품·건축 디자인업, 과학·기술 R&D 연구소",
    43: "카페, 요식업, 베이커리, 주점업, 숙박업, 식품조달",
    44: "병원, 약국, 심리상담, 피부관리, 미용실, 네일샵, 사우나, 꽃꽂이, 산후조리",
    45: "법무, 보안, 웨딩, 장례, 종교, 돌봄서비스, 서비스업, 온라인 소셜네트워킹",
}

# (대분류명, 소속 NICE류 목록) — id는 순서대로 1부터 부여.
_CATEGORIES: list[tuple[str, list[int]]] = [
    ("전체분류", list(range(1, 46))),
    ("요식업/식음료", [5, 9, 21, 29, 30, 31, 32, 33, 35, 39, 40, 41, 43, 44]),
    ("의류/패션/쇼핑몰", [9, 14, 18, 23, 24, 25, 26, 28, 35, 40, 41, 42, 45]),
    ("뷰티/미용/화장품", [3, 4, 5, 8, 10, 11, 21, 26, 35, 41, 42, 44]),
    ("의료/제약/복지", [3, 5, 10, 29, 35, 36, 40, 41, 42, 43, 44, 45]),
    ("여행/스포츠/취미", [9, 11, 12, 15, 18, 21, 22, 24, 25, 28, 35, 39, 41, 43]),
    ("교육/엔터테인먼트/유튜버", [9, 16, 21, 25, 28, 35, 38, 41, 42]),
    ("생활/편의서비스", [9, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45]),
    ("생활용품/가구/가전제품", [3, 4, 5, 7, 8, 9, 11, 16, 20, 21, 24, 27, 35]),
    ("출산/유아동", [3, 5, 9, 10, 12, 16, 18, 20, 21, 24, 25, 27, 28, 30, 35, 41]),
    ("반려/애완용품", [3, 5, 6, 9, 12, 16, 18, 20, 21, 28, 31, 35, 41, 43, 44, 45]),
    ("차량/오토", [1, 3, 4, 5, 9, 12, 17, 27, 28, 35, 37, 39, 43]),
    ("인테리어/건축/부동산", [2, 6, 11, 17, 19, 20, 27, 35, 36, 37, 40, 42]),
    ("과학/환경/법률", [1, 2, 4, 7, 9, 11, 12, 35, 37, 39, 40, 42, 44, 45]),
    ("IT/플랫폼/APP", [7, 9, 12, 35, 36, 37, 38, 39, 41, 42, 44, 45]),
]


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = insp.get_table_names()

    if "kinds" not in existing_tables:
        op.create_table(
            "kinds",
            sa.Column("id", sa.SmallInteger, primary_key=True),
            sa.Column("description", sa.Text, nullable=False),
        )
    if "categories" not in existing_tables:
        op.create_table(
            "categories",
            sa.Column("id", sa.SmallInteger, primary_key=True),
            sa.Column("name", sa.Text, nullable=False, unique=True),
        )
    if "category_kinds" not in existing_tables:
        op.create_table(
            "category_kinds",
            sa.Column(
                "category_id",
                sa.SmallInteger,
                sa.ForeignKey("categories.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "kind_id",
                sa.SmallInteger,
                sa.ForeignKey("kinds.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("category_id", "kind_id"),
        )
        op.create_index("idx_category_kinds_kind", "category_kinds", ["kind_id"])

    # 데이터 시딩 — 이미 채워져 있으면 스킵(멱등).
    kinds_tbl = sa.table("kinds", sa.column("id"), sa.column("description"))
    if bind.execute(sa.text("SELECT count(*) FROM kinds")).scalar() == 0:
        op.bulk_insert(kinds_tbl, [{"id": k, "description": v} for k, v in _KINDS.items()])

    categories_tbl = sa.table("categories", sa.column("id"), sa.column("name"))
    if bind.execute(sa.text("SELECT count(*) FROM categories")).scalar() == 0:
        op.bulk_insert(
            categories_tbl,
            [{"id": i, "name": name} for i, (name, _kinds) in enumerate(_CATEGORIES, start=1)],
        )

    category_kinds_tbl = sa.table("category_kinds", sa.column("category_id"), sa.column("kind_id"))
    if bind.execute(sa.text("SELECT count(*) FROM category_kinds")).scalar() == 0:
        rows = [
            {"category_id": i, "kind_id": k}
            for i, (_name, kinds) in enumerate(_CATEGORIES, start=1)
            for k in kinds
        ]
        op.bulk_insert(category_kinds_tbl, rows)


def downgrade() -> None:
    op.drop_table("category_kinds")
    op.drop_table("categories")
    op.drop_table("kinds")
