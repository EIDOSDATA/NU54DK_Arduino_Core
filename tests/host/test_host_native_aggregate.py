"""! @brief source·attempt·OS·shard 혼합과 실제 image 차이를 집계에서 거부합니다. """
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

from tests.host.test_host_artifact_semantics import arm_image, ihex

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('host_native_aggregate_unit', ROOT / 'tools/ci/host_native_package_aggregate.py')
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)


class HostNativeAggregateTests(unittest.TestCase):
    """! @brief synthetic fixture의 단위 검사이며 실제 native build·HIL 증거가 아닙니다. """

    def setUp(self):
        """! @brief 임시 artifact와 명시한 source·version fixture를 준비합니다. """
        self.temporary = tempfile.TemporaryDirectory(prefix='native-aggregate-unit-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = '1' * 40
        self.version = '0.6.0-host.1'

    def record(self, platform, shard=0, mode='smoke'):
        """! @brief source·실행 identity가 명시된 최소 집계 protocol fixture입니다. """
        return {'source_revision': self.source, 'version': self.version, 'mode': mode, 'status': 'PASS',
            'shard_index': shard, 'shard_count': 8, 'hardware_operations': 0, 'user_physical_OS_gate': 'NOT_RUN',
            'context': {'platform_key': platform, 'source_revision': self.source, 'version': self.version,
                'host': {'native': True}, 'workflow_run_id': '123', 'workflow_run_attempt': 1}}

    def image_rows(self):
        """! @brief debug byte만 다른 실제 ARM ELF·동일 HEX 파일을 작성합니다. """
        rows = {}
        for number, platform in enumerate(sorted(A.PLATFORMS)):
            elf = self.root / (platform + '.elf')
            image = self.root / (platform + '.hex')
            elf.write_bytes(arm_image(debug=bytes([65 + number]) * 4))
            image.write_text(ihex(0, 0, b'ABCD') + ihex(1), encoding='ascii')
            rows[platform] = {'identity': 'NUCODE_NU54DK/Blink', 'profile': 'standard', 'sysbuild': False,
                'status': 'PASS', 'ELF': A.S.elf_semantics(elf), 'HEX': A.S.hex_semantics(image),
                'resource_audit': {'flash': {'used_bytes': 4}, 'ram': {'used_bytes': 0},
                    'regions': {}, 'budget': {}, 'forbidden_symbols': []}}
        return rows

    def test_native_three_OS_and_complete_shards_are_both_required(self):
        """! @brief 세 OS smoke와 모든24개 shard를 각각 고정 분모로 판정합니다. """
        smoke = [self.record(platform) for platform in A.PLATFORMS]
        self.assertEqual(set(A.partition(smoke, self.source, self.version, 'smoke')), A.PLATFORMS)
        full = [self.record(platform, shard, 'examples') for platform in A.PLATFORMS for shard in range(8)]
        self.assertTrue(all(len(rows) == 8 for rows in A.partition(full, self.source, self.version, 'examples').values()))
        for damaged in (smoke[:-1], full[:-1], full + [full[0]]):
            with self.assertRaises(ValueError):
                A.partition(damaged, self.source, self.version, 'smoke' if len(damaged) == 2 else 'examples')

    def test_different_source_attempt_or_duplicate_shard_cannot_fill_the_matrix(self):
        """! @brief 일부 성공을 다른 source·attempt·중복 shard로 채우지 못합니다. """
        baseline = [self.record(platform, shard, 'examples') for platform in A.PLATFORMS for shard in range(8)]
        mutations = (
            lambda rows: rows[0].update(source_revision='2' * 40),
            lambda rows: rows[0]['context'].update(workflow_run_attempt=2),
            lambda rows: rows[0].update(shard_index=1),
            lambda rows: rows[0].update(shard_index=False),
            lambda rows: rows[0].update(status='FAIL'),
        )
        for mutate in mutations:
            rows = copy.deepcopy(baseline)
            mutate(rows)
            with self.assertRaises(ValueError):
                A.partition(rows, self.source, self.version, 'examples')

    def test_debug_only_difference_keeps_auditable_original_hashes(self):
        """! @brief debug 차이를 숨기지 않고 원형 hash를 남기며 load image를 비교합니다. """
        compared = A.compare_images(self.image_rows())
        self.assertEqual(compared['status'], 'PASS')
        self.assertEqual(len(set(compared['ELF_original_sha256'].values())), 3)
        self.assertEqual(compared['flash_bytes'], 4)

    def test_changed_instruction_or_memory_budget_fails_comparison(self):
        """! @brief 서로 다른 실제 명령과 RAM 사용량을 동일 firmware로 합치지 않습니다. """
        rows = self.image_rows()
        path = self.root / 'changed.elf'
        path.write_bytes(arm_image(text=b'\x01\xbf\x70\x47'))
        rows['macos-arm64']['ELF'] = A.S.elf_semantics(path)
        with self.assertRaises(ValueError):
            A.compare_images(rows)
        rows = self.image_rows()
        rows['linux-x86_64']['resource_audit']['ram']['used_bytes'] = 1
        with self.assertRaises(ValueError):
            A.compare_images(rows)

    def test_signed_fixture_needs_verified_identical_payload_and_single_mask(self):
        """! @brief CI 서명 차이는 검증된 payload와 정확한 public key 범위에서만 분리합니다. """
        rows = self.image_rows()
        for row in rows.values():
            row.update(sysbuild=True, profile='secure_ble_dfu',
                signature_verification={'status': 'PASS', 'CI_fixture_only': True,
                    'image_digest_sha256': 'a' * 64, 'image_version': [1, 0, 0, 0]},
                boot_HEX={'normalized_fixture_sha256': 'b' * 64, 'fixture_masked_ranges': [{'address': 8, 'size': 91}]})
        self.assertEqual(A.compare_images(rows)['status'], 'PASS')
        for mutate in (lambda row: row['signature_verification'].update(status='FAIL'),
                lambda row: row['signature_verification'].update(image_digest_sha256='c' * 64),
                lambda row: row['boot_HEX'].update(fixture_masked_ranges=[])):
            damaged = copy.deepcopy(rows)
            mutate(damaged['linux-x86_64'])
            with self.assertRaises(ValueError):
                A.compare_images(damaged)

    def test_relative_artifact_cannot_read_outside_the_downloaded_worker(self):
        """! @brief worker 밖의 파일을 artifact로 대신 읽지 않습니다. """
        (self.root / 'targets').mkdir()
        (self.root / 'targets/app.elf').write_bytes(b'fixture')
        self.assertEqual(A.artifact_path(self.root, 'targets/app.elf', 'targets'), self.root / 'targets/app.elf')
        for value in ('../outside', '/absolute', 'C:/outside', r'targets\escape', 'logs/other'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                A.artifact_path(self.root, value, 'targets')


if __name__ == '__main__':
    unittest.main()
