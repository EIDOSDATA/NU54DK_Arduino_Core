"""! @brief 분리된 BLE production 파일의 명시적 목록을 기존 source 계약에 제공합니다. """
from pathlib import Path
import re
ROOT = Path(__file__).resolve().parents[2]


def gap_source():
    """! @brief 누락된 파일은 실패시키며 GAP 구현과 공유 상태를 함께 읽습니다. """
    base = ROOT / 'libraries/NUCODE_BLE/src'
    names = ['internal/gap/GapInternal.h', 'internal/gap/GapScanning.cpp',
             'internal/gap/GapConnection.cpp', 'internal/gap/GapAdvertising.cpp',
             'internal/gap/GapValues.cpp', 'NUCODE_BLE_GAP.cpp']
    return '\n'.join((base / name).read_text(encoding='utf-8') for name in names)


def gatt_source():
    """! @brief 명시적 GATT 파일을 읽고 private 소유 accessor 이름만 정규화합니다. """
    base = ROOT / 'libraries/NUCODE_BLE/src'
    header = (base / 'internal/gatt/GattInternal.h').read_text(encoding='utf-8')
    header = header[:header.index('/** @brief 내부 module 간 호출')]
    names = ['internal/gatt/GattServer.cpp', 'internal/gatt/GattClient.cpp',
             'internal/gatt/GattDatabase.cpp', 'NUCODE_BLE_GATT.cpp']
    source = header + '\n' + '\n'.join((base / name).read_text(encoding='utf-8') for name in names)
    source = re.sub(r'(?:databaseState|serverState|sessionState|clientState)\(\)\s*\.\s*', '', source)
    return source.replace('serviceSlots()', 'service_slots').replace('&gattEventQueue()', '&gatt_event_queue')
