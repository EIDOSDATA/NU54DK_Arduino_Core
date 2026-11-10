#!/usr/bin/env python3
"""! @brief 같은 source의 native 세 OS·전체 shard와 실제 target artifact만 집계합니다. """
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('native_package_aggregate_consumer', Path(__file__).with_name('host_native_package_consumer.py'))
C = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = C
spec.loader.exec_module(C)
P, S = C.P, C.S
PLATFORMS = {'windows-x86_64', 'linux-x86_64', 'macos-arm64'}


def require(condition: bool, message: str):
    """! @brief 누락·중복·다른 source 실적은 성공으로 조합하지 않습니다. """
    if not condition:
        raise ValueError(message)


def read_json(path: Path):
    """! @brief 집계 입력의 중복 JSON key를 거부합니다. """
    def pairs(items):
        """! @brief object별 중복 key를 확인합니다. """
        result = {}
        for key, value in items:
            require(key not in result, '집계 JSON key가 중복됐습니다: ' + key)
            result[key] = value
        return result
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=pairs)


def artifact_path(base: Path, relative: str, prefix: str) -> Path:
    """! @brief artifact 자체 밖의 절대·drive·상위 경로를 읽지 않습니다. """
    require(isinstance(relative, str), 'artifact 상대 경로가 문자열이 아닙니다.')
    path = PurePosixPath(relative)
    require(not path.is_absolute() and not PureWindowsPath(relative).drive and '..' not in path.parts
        and '\\' not in relative and path.parts and path.parts[0] == prefix,
        'artifact 상대 경계가 다릅니다.')
    actual = base.joinpath(*path.parts)
    require(actual.is_file() and not actual.is_symlink() and actual.resolve().is_relative_to(base.resolve()),
        'artifact 파일이 누락됐거나 외부를 가리킵니다.')
    return actual


def partition(records: list[dict], source: str, version: str, mode: str) -> dict[str, list[dict]]:
    """! @brief 세 OS·8분할 분모를 source·version·실제 완료 상태와 함께 고정합니다. """
    grouped = {key: [] for key in PLATFORMS}
    per_os = 1 if mode == 'smoke' else C.SHARDS
    require(len(records) == 3 * per_os, 'native OS/shard 결과 수가 다릅니다.')
    for row in records:
        key = row.get('context', {}).get('platform_key')
        require(key in PLATFORMS and row.get('source_revision') == source and row.get('version') == version
            and row.get('mode') == mode and row.get('status') == 'PASS'
            and row['context'].get('source_revision') == source and row['context'].get('version') == version
            and row['context'].get('host', {}).get('native') is True
            and row.get('hardware_operations') == 0 and row.get('user_physical_OS_gate') == 'NOT_RUN',
            '다른 source·version·Host 또는 미완료 결과를 합칠 수 없습니다.')
        require(type(row.get('shard_index')) is int and type(row.get('shard_count')) is int,
            'shard 번호·분모는 실제 정수여야 합니다.')
        require(isinstance(row['context'].get('workflow_run_id'), str)
            and re.fullmatch(r'[1-9][0-9]*', row['context']['workflow_run_id']) is not None
            and type(row['context'].get('workflow_run_attempt')) is int and row['context']['workflow_run_attempt'] >= 1,
            '실제 workflow run·attempt identity가 없습니다.')
        grouped[key].append(row)
    require(len({(row['context'].get('workflow_run_id'), row['context'].get('workflow_run_attempt')) for row in records}) == 1,
        '서로 다른 workflow run·attempt를 합칠 수 없습니다.')
    for key, rows in grouped.items():
        require(len(rows) == per_os, '필수 OS 결과가 누락됐습니다: ' + key)
        expected = {0} if mode == 'smoke' else set(range(C.SHARDS))
        require({row.get('shard_index') for row in rows} == expected
            and all(row.get('shard_count') == C.SHARDS for row in rows), '동일 OS의 shard가 누락·중복됐습니다: ' + key)
    return grouped


def compare_images(rows: dict[str, dict]) -> dict:
    """! @brief 실제 load byte·예산을 비교하며 CI 서명 fixture 차이만 명시적으로 분리합니다. """
    require(set(rows) == PLATFORMS, 'image 비교에 필요한 세 Host가 없습니다.')
    base = rows['windows-x86_64']
    for key, row in rows.items():
        require(row['identity'] == base['identity'] and row['profile'] == base['profile'] and row['sysbuild'] is base['sysbuild'],
            '예제·profile·image 방식이 서로 다릅니다: ' + key)
        require(row['ELF']['load_sha256'] == base['ELF']['load_sha256']
            and row['ELF']['allocated_sections'] == base['ELF']['allocated_sections'],
            'Host별 실제 ARM load image가 다릅니다: ' + base['identity'] + ':' + key)
        for field in ('flash', 'ram', 'regions', 'budget', 'forbidden_symbols'):
            require(row['resource_audit'].get(field) == base['resource_audit'].get(field),
                'Host별 실제 memory 예산·경계가 다릅니다: ' + base['identity'] + ':' + key + ':' + field)
        if not base['sysbuild']:
            require(row['HEX']['data_sha256'] == base['HEX']['data_sha256']
                and row['HEX']['start_records'] == base['HEX']['start_records'],
                'Host별 실제 unsigned HEX byte가 다릅니다: ' + base['identity'] + ':' + key)
        else:
            signature = row.get('signature_verification', {})
            require(signature.get('status') == 'PASS' and signature.get('CI_fixture_only') is True
                and signature.get('image_digest_sha256') == base.get('signature_verification', {}).get('image_digest_sha256')
                and signature.get('image_version') == base.get('signature_verification', {}).get('image_version')
                and row.get('boot_HEX', {}).get('normalized_fixture_sha256') == base.get('boot_HEX', {}).get('normalized_fixture_sha256')
                and len(row.get('boot_HEX', {}).get('fixture_masked_ranges', [])) == 1,
                'DFU 인증 payload·실제 서명 검증·boot public fixture 비교가 다릅니다: ' + base['identity'] + ':' + key)
    return {'identity': base['identity'], 'profile': base['profile'], 'status': 'PASS',
        'comparison_scope': 'IDENTICAL_AUTHENTICATED_APP_AND_BOOT_EXCEPT_DECLARED_CI_PUBLIC_KEY' if base['sysbuild']
            else 'IDENTICAL_ARM_LOAD_AND_NORMALIZED_UNSIGNED_HEX',
        'ARM_load_sha256': base['ELF']['load_sha256'],
        'ELF_original_sha256': {key: row['ELF']['file_sha256'] for key, row in sorted(rows.items())},
        'HEX_original_sha256': {key: row['HEX']['file_sha256'] for key, row in sorted(rows.items())},
        'flash_bytes': base['resource_audit']['flash']['used_bytes'], 'ram_bytes': base['resource_audit']['ram']['used_bytes']}


def validate_build(base: Path, row: dict, context: dict, pins: dict) -> dict:
    """! @brief JSON 주장 대신 복사된 실제 ELF·HEX·manifest·로그의 byte를 다시 검사합니다. """
    require(row.get('status') == 'PASS' and type(row.get('actual_exit_code')) is int and row['actual_exit_code'] == 0,
        '실제 compile exit0·완료 결과가 아닙니다.')
    outputs = row.get('outputs', {})
    required = {'elf', 'hex', 'manifest'} | ({'bin', 'boot.hex'} if row.get('sysbuild') is True else set())
    require(set(outputs) == required, '필수 target 원형 파일이 누락되거나 다른 파일이 있습니다.')
    files = {}
    for key, record in outputs.items():
        path = artifact_path(base, record['path'], 'targets')
        require(P.sha(path) == record['sha256'] and path.stat().st_size == record['size'], 'target 원형 파일 hash·size가 다릅니다.')
        files[key] = path
    require(S.elf_semantics(files['elf']) == row['ELF'] and S.hex_semantics(files['hex']) == row['HEX'],
        '실제 ELF·HEX 분석과 결과 metadata가 다릅니다.')
    log = artifact_path(base, row['log'], 'logs')
    require(P.sha(log) == row['log_sha256'] and b'HOST_FORBIDDEN_SYSTEM_TOOL:' not in log.read_bytes(), 'compile 원형 로그가 다릅니다.')
    manifest = read_json(files['manifest'])
    inputs = manifest.get('cache', {}).get('input_manifest', {})
    require(inputs.get('adapter', {}).get('embedded_core_revision') == context['source_revision']
        and inputs.get('ncs', {}).get('nrf_revision') == pins['ncs']['revision']
        and inputs.get('ncs', {}).get('zephyr_revision') == pins['zephyr']['revision']
        and inputs.get('board_package', {}).get('revision') == pins['board_revision']
        and inputs.get('toolchain', {}).get('bundle_id') == context['bundle_id']
        and manifest.get('fqbn') == 'nucode:zephyr:nu54dk:feature_set=' + row['profile']
        and manifest.get('resource_audit') == row['resource_audit']
        and manifest.get('sysbuild') is row['sysbuild'], '원형 manifest의 source·SDK·profile·실측 예산 결합이 다릅니다.')
    for key in required - {'manifest'}:
        record = manifest.get('artifacts', {}).get(key, {})
        require(record.get('sha256') == outputs[key]['sha256'] and record.get('size') == outputs[key]['size'],
            '원형 manifest가 다른 artifact generation을 가리킵니다.')
    if row['sysbuild']:
        fixture = context['signing_fixture']
        public = bytes.fromhex(fixture['public_key_der_hex'])
        require(hashlib.sha256(public).hexdigest() == fixture['public_key_sha256']
            and S.hex_semantics(files['boot.hex'], public) == row['boot_HEX']
            and row['signature_verification']['public_key_sha256'] == fixture['public_key_sha256'],
            '실제 boot image·서명 fixture의 public key가 다릅니다.')
        number = files['elf'].parent.name
        verify_log = artifact_path(base, 'logs/verify-signed-' + number + '.log', 'logs')
        require(P.sha(verify_log) == row['signature_verification_log_sha256'], '원형 SDK 서명 검증 로그가 다릅니다.')
        verification = read_json(verify_log)
        require(verification == row['signature_verification'], 'SDK의 실제 서명 검증 출력이 다릅니다.')
    return row


def aggregate(producer_dir: Path, results_dir: Path, source: str, mode: str) -> dict:
    """! @brief 같은 source의 package·ready·204분모·9개 거부 조건과 artifact를 한 번만 집계합니다. """
    require(P.git(ROOT, 'rev-parse', 'HEAD') == source, 'aggregate checkout source가 다릅니다.')
    producer = read_json(producer_dir / 'producer.json')
    require(producer['source_revision'] == source and producer['reproducible_bytes'] is True, 'producer source 또는 재현성이 다릅니다.')
    paths = sorted(path for path in results_dir.rglob('result.json') if path.parent.name == 'reports')
    records = [read_json(path) for path in paths]
    grouped = partition(records, source, producer['version'], mode)
    package = P.load_package()
    package.configure_release_candidates(package.RELEASE_CANDIDATE_VERSIONS + (producer['version'],))
    archive = producer_dir / 'package' / producer['archive']['filename']
    require(P.sha(archive) == producer['archive']['sha256'], 'producer archive byte가 다릅니다.')
    manifest = package.validate_archive(archive, expected_version=producer['version'], expected_commit=source)
    pins = read_json(ROOT / 'tools/nu54-prerequisites/platform-pins.json')
    catalog = C.EXAMPLES.load_catalog(ROOT)
    ordered = sorted(catalog, key=str.casefold)
    locations = {id(row): path.parent.parent for row, path in zip(records, paths, strict=True)}
    images = {key: {} for key in PLATFORMS}
    summaries = {}
    for key, workers in grouped.items():
        negatives_seen = set()
        for result in workers:
            base = locations[id(result)]
            context = result['context']
            require(read_json(base / 'reports/context.json') == context, '독립 context와 result가 다릅니다.')
            require(context.get('archive_sha256') == producer['archive']['sha256']
                and context.get('bootstrap_pins_sha256') == producer['bootstrap_pins_sha256']
                and context.get('platform_prerequisites_sha256') == producer['platform_prerequisites_sha256'],
                '다른 package·bootstrap·SDK pin의 worker를 합칠 수 없습니다.')
            ready = read_json(base / 'reports/stored-verification.json')
            require(ready.get('source_revision') == source and ready.get('status') == 'ready' and ready.get('platform_key') == key
                and ready.get('platform_pins_sha256') == producer['platform_prerequisites_sha256']
                and ready.get('backend_sha256') == manifest['file_hashes']['tools/nu54-builder/src/nu54_builder_impl/prerequisites.py']
                and ready.get('toolchain_bundle_id') == pins['platforms'][key]['toolchain']['bundle_id']
                and context['bundle_id'] == ready['toolchain_bundle_id'] and ready.get('nrfutil_version') == '8.2.1'
                and ready.get('sdk_manager_version') == '1.16.1', '다른 source·pin·bundle의 SDK 상태를 합칠 수 없습니다.')
            shard = result['shard_index']
            expected = ['NUCODE_NU54DK/Blink'] if mode == 'smoke' else [identity for number, identity in enumerate(ordered) if number % C.SHARDS == shard]
            require(result.get('assigned_identities') == expected and result.get('summary', {}).get('discovered') == 204
                and result.get('summary', {}).get('assigned') == len(expected) and result['summary'].get('passed') == len(expected)
                and result['summary'].get('failed') == 0, '실제 발견·배정·성공 분모가 다릅니다.')
            builds = result.get('builds', [])
            require([row['identity'] for row in builds] == expected, 'shard의 예제가 누락·중복됐습니다.')
            for row in builds:
                require(row['identity'] not in images[key] and row['profile'] == catalog[row['identity']]['profile'], '예제 중복 또는 다른 profile입니다.')
                images[key][row['identity']] = validate_build(base, row, context, pins)
            required_negative = [] if mode == 'smoke' else [case for number, case in enumerate(C.EXAMPLES.NEGATIVE_PROFILE_MATRIX) if number % C.SHARDS == shard]
            negatives = result.get('negative_profiles', [])
            require([row['id'] for row in negatives] == [case['id'] for case in required_negative], 'profile 거부 조건이 누락·중복됐습니다.')
            for row, expected_case in zip(negatives, required_negative, strict=True):
                require(row['status'] == 'PASS' and row.get('expected_rejection') is True
                    and type(row.get('actual_exit_code')) is int and row['actual_exit_code'] != 0
                    and all(row[field] == expected_case[field] for field in ('id', 'identity', 'profile')),
                    '실제 profile 거부 결과가 아닙니다.')
                log = artifact_path(base, row['log'], 'logs')
                require(P.sha(log) == row['log_sha256'] and expected_case['marker'].encode() in log.read_bytes()
                    and b'HOST_FORBIDDEN_SYSTEM_TOOL:' not in log.read_bytes(), '원형 profile 거부 marker·로그가 다릅니다.')
                require(row['id'] not in negatives_seen, 'profile 거부 조건이 중복됐습니다.')
                negatives_seen.add(row['id'])
        expected_count = 1 if mode == 'smoke' else 204
        require(len(images[key]) == expected_count, 'OS별 실제 compile 전체 분모가 다릅니다.')
        summaries[key] = {'compiled': len(images[key]), 'negative_profile_rejections': len(negatives_seen), 'workers': len(workers)}
    identities = ['NUCODE_NU54DK/Blink'] if mode == 'smoke' else ordered
    compared = [compare_images({key: images[key][identity] for key in PLATFORMS}) for identity in identities]
    return {'schema_version': 1, 'kind': 'HOST_NATIVE_PACKAGE_AGGREGATE', 'status': 'PASS', 'source_revision': source,
        'version': producer['version'], 'mode': mode, 'platforms': summaries, 'compared_examples': len(compared),
        'comparisons': compared, 'source_credits_combined': False, 'hardware_operations': 0,
        'user_physical_OS_gate': 'NOT_RUN', 'observed_utc': datetime.now(timezone.utc).isoformat()}


def main() -> int:
    """! @brief 원형 결과는 수정하지 않고 새 비교 receipt만 작성합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument('--producer', type=Path, required=True)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--mode', choices=('smoke', 'examples'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = aggregate(args.producer, args.results, args.source, args.mode)
    except Exception as error:
        result = {'schema_version': 1, 'kind': 'HOST_NATIVE_PACKAGE_AGGREGATE', 'status': 'FAIL',
            'source_revision': args.source, 'mode': args.mode, 'error_type': type(error).__name__,
            'error': str(error), 'source_credits_combined': False, 'hardware_operations': 0,
            'user_physical_OS_gate': 'NOT_RUN', 'observed_utc': datetime.now(timezone.utc).isoformat()}
    C.write_json(args.output, result)
    print(json.dumps({'status': result['status'], 'source_revision': args.source, 'mode': args.mode,
        'compared_examples': result.get('compared_examples'), 'error': result.get('error')}, ensure_ascii=False))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
