"""! @brief RC 원형 누락·변조를 tooling import와 장치 접근 전에 거부하는지 검사합니다. """
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('host_rc_entry_test',ROOT/'tools/release/host_rc_entry.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class HostRcEntryTests(unittest.TestCase):
    """! @brief 임시 kit 파일만 사용하며 실제 SDK·장치를 열지 않습니다. """
    def make_kit(self,root):
        """! @brief 원형 hash를 기록한 최소 진입점·전이 입력을 만듭니다. """
        kit = root/'kit'
        required = ['source/tools/release/host_rc_entry.py','source/tools/release/host_native_lifecycle.py',
            'payload/current/producer.json','payload/previous/producer.json','source.tar','START.cmd','START.sh']
        rows = []
        for name in required:
            path = kit/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(b'fixture-original-bytes')
            rows.append(dict(path=name,size=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        data = dict(kind='UNPUBLISHED_PRIVATE_HOST_RC1_KIT',version='0.6.0-rc.1',
            source_revision='a'*40,expected_technical_source='a'*40,files=rows)
        (kit/'kit-manifest.json').write_text(json.dumps(data),encoding='utf-8')
        return kit,data

    def test_corrupt_tooling_is_rejected_before_import(self):
        """! @brief hash가 달라진 tooling은 Python code로 읽지 않습니다. """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            kit,data = self.make_kit(root)
            (kit/'source/tools/release/host_native_lifecycle.py').write_text('raise RuntimeError("MUST_NOT_EXECUTE")',encoding='utf-8')
            with mock.patch.object(M,'ROOT',kit/'source'),mock.patch.object(M,'load',side_effect=AssertionError('tooling imported')) as imported:
                with self.assertRaisesRegex(ValueError,'원형 byte 불일치'):
                    M.main(['--kit',str(kit),'--work-root',str(root/'work'),'plan'])
                imported.assert_not_called()
            self.assertFalse((root/'work').exists())

    def test_missing_required_entries_are_not_a_valid_empty_kit(self):
        """! @brief 빈 원장은 모든 hash가 맞는다는 이유로 통과하지 못합니다. """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            kit,data = self.make_kit(root)
            with mock.patch.object(M,'ROOT',kit/'source'):
                self.assertEqual(M.verify_kit(kit)['source_revision'],'a'*40)
                data['files'] = []
                (kit/'kit-manifest.json').write_text(json.dumps(data),encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'필수 도구'):
                    M.verify_kit(kit)


if __name__=='__main__':
    unittest.main()
