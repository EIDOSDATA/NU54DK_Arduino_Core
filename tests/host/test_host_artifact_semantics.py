"""! @brief debug-only 차이를 실제 ARM load byte·주소 변경과 구분합니다. """
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('host_artifact_semantics_test', ROOT / 'tools/ci/host_artifact_semantics.py')
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)


def arm_image(text=b'\x00\xbf\x70\x47', debug=b'AAAA'):
    """! @brief 실행 segment와 비할당 debug section을 가진 최소 ARM ELF fixture를 만듭니다. """
    data = bytearray(672)
    names = b'\0.text\0.debug\0.shstrtab\0'
    data[:52] = struct.pack('<16sHHIIIIIHHHHHH', b'\x7fELF\x01\x01\x01' + b'\0' * 9,
        2, 40, 1, 0x10001, 52, 512, 0x5000200, 52, 32, 1, 40, 4, 3)
    data[52:84] = struct.pack('<IIIIIIII', 1, 256, 0x10000, 0x10000, 4, 4, 5, 4)
    data[256:260] = text
    data[264:268] = debug
    data[320:320 + len(names)] = names
    rows = [(0,) * 10, (1, 1, 6, 0x10000, 256, 4, 0, 0, 4, 0),
        (7, 1, 0, 0, 264, 4, 0, 0, 1, 0), (14, 3, 0, 0, 320, len(names), 0, 0, 1, 0)]
    for index, row in enumerate(rows):
        data[512 + 40 * index:552 + 40 * index] = struct.pack('<IIIIIIIIII', *row)
    return bytes(data)


def ihex(kind, address=0, body=b''):
    """! @brief 분석기의 결과를 사용하지 않고 표준 Intel HEX record를 작성합니다. """
    record = bytes([len(body)]) + address.to_bytes(2, 'big') + bytes([kind]) + body
    return ':' + (record + bytes([-sum(record) & 255])).hex().upper() + '\n'


class HostArtifactSemanticsTests(unittest.TestCase):
    """! @brief 실제 파일의 checksum·경계·load segment·중첩 의미를 검사합니다. """

    def setUp(self):
        """! @brief 각 시험의 artifact를 외부 임시 root에 둡니다. """
        self.temporary = tempfile.TemporaryDirectory(prefix='host-artifact-semantics-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_debug_bytes_do_not_hide_actual_loaded_instruction_change(self):
        """! @brief debug 차이는 분리하지만 실제 명령 byte 변화는 반드시 검출합니다. """
        rows = []
        for index, body in enumerate((arm_image(), arm_image(debug=b'BBBB'), arm_image(text=b'\x01\xbf\x70\x47'))):
            path = self.root / f'{index}.elf'
            path.write_bytes(body)
            rows.append(S.elf_semantics(path))
        self.assertNotEqual(rows[0]['file_sha256'], rows[1]['file_sha256'])
        self.assertEqual(rows[0]['load_sha256'], rows[1]['load_sha256'])
        self.assertEqual(rows[0]['allocated_sections'], rows[1]['allocated_sections'])
        self.assertNotEqual(rows[0]['load_sha256'], rows[2]['load_sha256'])

    def test_invalid_machine_table_and_truncated_segment_are_rejected(self):
        """! @brief 잘못된 architecture·table 경계·부분 파일을 load 성공으로 해석하지 않습니다. """
        cases = [b'not ELF', arm_image()[:258]]
        wrong = bytearray(arm_image())
        struct.pack_into('<H', wrong, 18, 62)
        cases.append(wrong)
        for index, body in enumerate(cases):
            path = self.root / f'bad-{index}.elf'
            path.write_bytes(body)
            with self.subTest(index=index), self.assertRaises(S.ArtifactFormatError):
                S.elf_semantics(path)

    def test_hex_line_order_and_split_preserve_the_same_target_bytes(self):
        """! @brief 기록 순서·줄 길이가 달라도 같은 실제 주소·byte를 비교합니다. """
        first = ihex(4, body=b'\x00\x01') + ihex(0, 0, b'ABCD') + ihex(1)
        second = ihex(4, body=b'\x00\x01') + ihex(0, 2, b'CD') + ihex(0, 0, b'AB') + ihex(1)
        rows = []
        for index, text in enumerate((first, second)):
            path = self.root / f'{index}.hex'
            path.write_text(text, encoding='ascii')
            rows.append(S.hex_semantics(path))
        self.assertNotEqual(rows[0]['file_sha256'], rows[1]['file_sha256'])
        self.assertEqual(rows[0]['data_sha256'], rows[1]['data_sha256'])
        self.assertEqual(rows[0]['ranges'], rows[1]['ranges'])

    def test_hex_bad_checksum_conflicting_overlap_and_missing_eof_fail(self):
        """! @brief 주소 충돌·손상·불완전 image를 정상화로 숨기지 않습니다. """
        cases = [ihex(0, 0, b'AB') + ihex(0, 1, b'X') + ihex(1),
            ihex(0, 0, b'AB'), ':02000000414200\n' + ihex(1)]
        for index, text in enumerate(cases):
            path = self.root / f'bad-{index}.hex'
            path.write_text(text, encoding='ascii')
            with self.subTest(index=index), self.assertRaises(S.ArtifactFormatError):
                S.hex_semantics(path)

    def test_only_the_declared_single_public_fixture_is_normalized(self):
        """! @brief 알려진 public fixture 외의 명령·데이터 변화는 마스킹으로 숨기지 않습니다. """
        rows = []
        for index, (key, suffix) in enumerate(((b'A' * 32, b'KEEP'), (b'B' * 32, b'KEEP'), (b'B' * 32, b'CHNG'))):
            path = self.root / f'key-{index}.hex'
            path.write_text(ihex(0, 0, b'CODE' + key + suffix) + ihex(1), encoding='ascii')
            rows.append(S.hex_semantics(path, key))
        self.assertNotEqual(rows[0]['data_sha256'], rows[1]['data_sha256'])
        self.assertEqual(rows[0]['normalized_fixture_sha256'], rows[1]['normalized_fixture_sha256'])
        self.assertNotEqual(rows[1]['normalized_fixture_sha256'], rows[2]['normalized_fixture_sha256'])
        for body in (b'CODE', b'A' * 64):
            path = self.root / 'missing-or-duplicate.hex'
            path.write_text(ihex(0, 0, body) + ihex(1), encoding='ascii')
            with self.assertRaises(S.ArtifactFormatError):
                S.hex_semantics(path, b'A' * 32)


if __name__ == '__main__':
    unittest.main()
