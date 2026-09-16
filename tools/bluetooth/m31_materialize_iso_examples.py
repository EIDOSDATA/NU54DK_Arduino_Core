#!/usr/bin/env python3
"""! @brief 이전의 시험용 ISO 예제 자동 생성을 명시적으로 차단합니다. """

from __future__ import annotations


## @brief 고정 시험 앱을 사용자 library로 복사하는 이전 절차를 거부합니다.
def materialize() -> None:
    raise RuntimeError(
        "고정 SDU/Serial oracle을 공개 ISO 예제로 복사할 수 없습니다. "
        "NUCODE_BLE_ISO 공개 데이터 API와 역할별 .ino를 작성하고 검증하세요."
    )


if __name__ == "__main__":
    materialize()
