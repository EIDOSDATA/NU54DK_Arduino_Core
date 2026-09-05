"""! @brief 분리된 BLE production 파일의 명시적 목록을 기존 source 계약에 제공합니다. """
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]


def gap_source():
    """! @brief 누락된 파일은 실패시키며 GAP 구현과 공유 상태를 함께 읽습니다. """
    base = ROOT / 'libraries/NUCODE_BLE/src'
    names = ['internal/gap/GapInternal.h', 'internal/gap/GapScanning.cpp',
             'internal/gap/GapConnection.cpp', 'internal/gap/GapAdvertising.cpp',
             'internal/gap/GapValues.cpp', 'NUCODE_BLE_GAP.cpp']
    return '\n'.join((base / name).read_text(encoding='utf-8') for name in names)
