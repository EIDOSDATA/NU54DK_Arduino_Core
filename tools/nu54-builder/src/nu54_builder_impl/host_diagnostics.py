"""! @brief 포트를 열거나 장치를 변경하지 않는 비식별 Host 설치 진단입니다. """
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Iterable

from .common import atomic_write_json
from .host import describe_host, require_supported_host
from .prerequisites import load_manifest, select_platform


def identity_hash(value: str | None) -> str | None:
    """! @brief 원시 serial·경로를 출력하지 않고 대조용 SHA-256만 반환합니다. """
    return hashlib.sha256(value.encode('utf-8')).hexdigest() if value else None


def serial_inventory(ports: Iterable[Any], host_os: str, by_id: Path = Path('/dev/serial/by-id')) -> list[dict[str, Any]]:
    """! @brief 실제 열거 port와 by-id를 익명 alias로 결합하며 포트는 열지 않습니다. """
    links: dict[str, list[str]] = {}
    if host_os == 'linux' and by_id.is_dir():
        for path in by_id.iterdir():
            if path.is_symlink():
                links.setdefault(str(path.resolve()), []).append(identity_hash(str(path)))
    rows = []
    for index, port in enumerate(sorted(ports, key=lambda item: item.device)):
        device = str(port.device)
        kind = next((name for name, pattern in (
            ('windows_vcom', r'COM\d+'), ('linux_acm', r'/dev/ttyACM\d+'),
            ('linux_usb', r'/dev/ttyUSB\d+'), ('macos_serial', r'/dev/(?:cu|tty)\..+'),
        ) if re.fullmatch(pattern, device, re.IGNORECASE)), 'other')
        row = {'alias': f'port-{index + 1}', 'kind': kind, 'path_sha256': identity_hash(device),
            'serial_sha256': identity_hash(getattr(port, 'serial_number', None)),
            'vid': getattr(port, 'vid', None), 'pid': getattr(port, 'pid', None),
            'device_open_attempted': False}
        if host_os == 'linux':
            row.update(by_id_path_sha256=sorted(links.get(str(Path(device).resolve()), [])),
                readable=os.access(device, os.R_OK), writable=os.access(device, os.W_OK))
        else:
            row['permission_status'] = 'NOT_VERIFIED_NO_DEVICE_OPEN'
        rows.append(row)
    return rows


def inspect_host(include_probes: bool = False) -> dict[str, Any]:
    """! @brief 의존 패키지·serial·선택적 CMSIS-DAP 열거만 수행하고 실기 PASS를 만들지 않습니다. """
    descriptor = require_supported_host(describe_host())
    key, pin = select_platform(load_manifest(), descriptor)
    result = {'schema_version': 1, 'kind': 'read_only_host_diagnostic', 'platform_key': key,
        'host': descriptor, 'device_open_attempted': False, 'flash_reset_halt_operations': 0,
        'user_physical_OS_gate': 'NOT_RUN', 'serial': {'status': 'NOT_RUN'},
        'probes': {'status': 'NOT_REQUESTED'}, 'system_dependencies': []}
    if descriptor['os'] == 'linux':
        for package in pin['system_dependencies']:
            observed = subprocess.run(['dpkg-query', '-W', '-f=${Version}', package],
                capture_output=True, text=True, timeout=10, check=False)
            result['system_dependencies'].append({'package': package, 'present': observed.returncode == 0,
                'version': observed.stdout.strip() if observed.returncode == 0 else None})
    try:
        from serial.tools import list_ports
        result['serial'] = {'status': 'ENUMERATED', 'ports': serial_inventory(list_ports.comports(), descriptor['os'])}
    except Exception as error:
        result['serial'] = {'status': 'ERROR', 'error_type': type(error).__name__}
    if include_probes:
        try:
            from .upload import discover_pyocd_probe_ids
            result['probes'] = {'status': 'ENUMERATED', 'identities_sha256':
                sorted(identity_hash(value) for value in discover_pyocd_probe_ids())}
        except Exception as error:
            result['probes'] = {'status': 'ERROR', 'error_type': type(error).__name__}
    return result


def main() -> int:
    """! @brief 진단 JSON을 출력하며 원시 UID·serial 경로·예외 원문을 노출하지 않습니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument('--include-probes', action='store_true')
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args()
    result = inspect_host(args.include_probes)
    if args.evidence:
        atomic_write_json(args.evidence, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    failed = result['serial']['status'] == 'ERROR' or result['probes']['status'] == 'ERROR'
    failed = failed or any(not row['present'] for row in result['system_dependencies'])
    return 1 if failed else 0
