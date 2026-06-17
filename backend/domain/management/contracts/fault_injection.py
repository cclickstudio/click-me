"""[이전 경로 호환 shim] FaultMode/FaultConfig 정본은 enums.py / schemas.py.

v2.0 §1: 고장 주입은 별도 파일 없이 기존 enums.py/schemas.py 안에서 해결한다.
기존 import 경로(🅰 mock.py·demo.py 포함)가 깨지지 않도록 재수출만 유지.
"""

from domain.management.contracts.enums import FaultMode
from domain.management.contracts.schemas import FaultConfig

__all__ = ["FaultConfig", "FaultMode"]
