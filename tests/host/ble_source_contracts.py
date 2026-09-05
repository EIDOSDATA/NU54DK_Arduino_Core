"""! @brief 분리된 BLE production 파일의 명시적 목록을 기존 source 계약에 제공합니다. """
from pathlib import Path
import re
ROOT = Path(__file__).resolve().parents[2]


def function_body(source, signature):
    """! @brief 파일 배치·들여쓰기와 무관하게 지정 함수의 중괄호 범위를 읽습니다. """
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


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


def security_source():
    """! @brief Security의 명시적 module 목록과 원래 상태 이름을 계약 검사에 제공합니다. """
    base = ROOT / 'libraries/NUCODE_BLE_Security/src'
    facade = (base / 'NUCODE_BLE_Security.cpp').read_text(encoding='utf-8')
    header = (base / 'internal/security/SecurityInternal.h').read_text(encoding='utf-8')
    header = header[:header.index('/** @brief 내부 module 호출')]
    names = ['SecurityHid.cpp', 'SecurityPairing.cpp', 'SecurityBond.cpp',
             'SecurityBattery.cpp', 'SecurityDeviceInformation.cpp']
    source = facade[:facade.index('namespace nucode::ble::internal::security')] + header + '\n'
    source += '\n'.join((base / 'internal/security' / name).read_text(encoding='utf-8') for name in names)
    source += '\n' + facade
    source = re.sub(r'(?:securityState|pairingState|bondStorage|hidState)\(\)\s*\.\s*', '', source)
    return source.replace('&securityEventQueue()', '&security_event_queue').replace(
        'unlockHidApi();', 'k_mutex_unlock(&hid_api_mutex);').replace(
        'lockHidApi();', 'k_mutex_lock(&hid_api_mutex, K_FOREVER);')
