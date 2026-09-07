"""! @brief 원본 batch와 세 개별 재실행을 구별하고 설치 예제 29개의 실산출물을 대조합니다. """
from pathlib import Path
import ast
import hashlib
import importlib.util
import json
import re
import shutil
import sys
import yaml

repo = Path('C:/Users/eidos/GitHub/NU54DK_Arduino_Core')
work = Path(__file__).parent
root = Path('C:/u4y')
platform = root / '검증 설치/hardware/nucode/zephyr'
proof = json.loads((work / 'verified-package-reproducibility.json').read_text(encoding='utf-8'))
tree = ast.parse((work / 'installed_examples.py').read_text(encoding='utf-8'))
definitions = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in ('sha', 'save', 'load', 'verify_identity')], type_ignores=[])
definitions = ast.fix_missing_locations(definitions)
exec(compile(definitions, str(work / 'installed_examples.py'), 'exec'), globals())
runner = load('installed_final_audit_runner', repo / 'tools/release/run_m27_package_examples.py')
lock = runner.load_example_lock()
records = []
retries = {2: ('retry-littlefs-final', 'installed-littlefs-final.log'),
           4: ('retry-gattperipheral', 'installed-gatt-retry.log'),
           23: ('retry-systemoffwake', 'installed-systemoff-retry.log')}
for sequence, example in enumerate(lock, 1):
    safe = re.sub(r'[^a-z0-9]+', '-', f"{example['library']}-{example['example']}".casefold()).strip('-')
    original = root / 'examples' / f'{sequence:02d}-{safe}'
    retried = sequence in retries
    build = root / retries[sequence][0] if retried else original
    manifest = build / (example['example'] + '.ino.nu54-build.json')
    sketch = platform / 'libraries' / example['library_directory'] / 'examples' / example['example']
    identity = runner.BASE.validate_build_manifest(
        manifest, example=example, sketch=sketch, build_root=build, platform_root=platform,
        ncs_root=Path('C:/Users/eidos/ncs/v3.4.0'),
        toolchain_root=Path('C:/Users/eidos/ncs/toolchains/dcbdc366a1'),
        cache_root=root / 'cache', forbidden_roots=(repo,),
    )
    destination = root / 'identity-records' / build.name
    if not destination.exists():
        verify_identity(manifest)
    preserved = json.loads((destination / 'verified.json').read_text(encoding='utf-8'))
    assert sha(manifest) == preserved['manifest_sha256']
    for item in preserved['artifacts'].values():
        path = Path(item['path'])
        assert sha(path) == item['sha256'] and path.stat().st_size == item['size']
    for item in preserved['source_inputs']['sources']:
        assert sha(Path(item['source_path'])) == item['sha256']
    for kind in ('live_record', 'configure_record'):
        assert sha(Path(preserved[kind]['path'])) == preserved[kind]['sha256']
    assert preserved['live_record']['identity']['core_revision'] == proof['source_commit']
    assert preserved['configure_record']['identity']['core-revision'] == proof['source_commit']
    original_log = root / 'examples/logs' / (original.name + '.log')
    log = work / retries[sequence][1] if retried else original_log
    records.append({'sequence': sequence, **example, 'status': 'passed',
                    'initial_batch_status': 'failed' if retried else 'passed',
                    'retry_without_product_source_change': retried,
                    'manifest': str(manifest), 'manifest_sha256': sha(manifest),
                    'build_log': str(log), 'build_log_sha256': sha(log),
                    'initial_log': str(original_log), 'initial_log_sha256': sha(original_log),
                    'preserved_identity_directory': str(destination), **identity})
assert len(records) == 29
batch = (work / 'installed-examples-final.log').read_text(encoding='utf-8')
assert 'M27_PACKAGE_EXAMPLES_FAIL' in batch
assert 'RETRY_GATT_EXIT=0' in (work / 'installed-gatt-retry.log').read_text(encoding='utf-8')
assert 'RETRY_LITTLEFS_EXIT=0' in (work / 'installed-littlefs-diagnostic.log').read_text(encoding='utf-8')
assert 'RETRY_LITTLEFS_EXIT=0' in (work / 'installed-littlefs-final.log').read_text(encoding='utf-8')
assert 'RETRY_SYSTEMOFF_EXIT=0' in (work / 'installed-systemoff-retry.log').read_text(encoding='utf-8')
save(root / 'examples-with-retries.json', {
    'source_commit': proof['source_commit'], 'package_version': '0.0.90',
    'status': 'passed-with-recorded-retries', 'initial_batch_status': 'failed',
    'initial_success_count': 26, 'retry_success_count': 3, 'compiled_count': 29,
    'all_live_and_configure_identities_verified': True, 'physical_executed': False,
    'is_rc_evidence': False, 'initial_failure_cause': 'not determined from terse compiler output',
    'littlefs_provenance_retry': 'First retry compiled successfully, but its cache entry was evicted before live/configure preservation. A fresh final retry preserved both records immediately.',
    'examples': records,
})
print('INSTALLED_29_ARTIFACTS_AND_SOURCE_IDENTITIES_PASS;INITIAL_BATCH_26_PASS_3_FAIL;RETRIES_3_PASS')
