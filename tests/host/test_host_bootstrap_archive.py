"""! @brief symlink-only 디렉터리 누락 회귀와 upstream byte·mode 보존을 검사합니다. """
import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('bootstrap_archive_unit', ROOT / 'packaging/boards-manager/nu54_package_impl/bootstrap_archive.py')
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)


class BootstrapArchiveTests(unittest.TestCase):
    """! @brief 실제 Arduino 실패 구조를 작은 archive로 재현하며 SDK 설치는 하지 않습니다. """

    def setUp(self):
        """! @brief 새 attempt마다 독립된 archive 경로를 생성합니다. """
        self.temporary = tempfile.TemporaryDirectory(prefix='bootstrap-archive-unit-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def upstream(self, link='../a/adm1178'):
        """! @brief 상위 directory entry가 없는 실제 terminfo와 같은 tar 구조를 만듭니다. """
        path = self.root / 'upstream.tar.gz'
        with tarfile.open(path, 'w:gz') as archive:
            for name, data, mode in (('python/bin/python3.12', b'fixture-executable', 0o755),
                    ('python/share/terminfo/a/adm1178', b'terminfo-bytes', 0o644)):
                item = tarfile.TarInfo(name)
                item.mode, item.size = mode, len(data)
                archive.addfile(item, io.BytesIO(data))
            item = tarfile.TarInfo('python/share/terminfo/1/1178')
            item.type, item.mode, item.linkname = tarfile.SYMTYPE, 0o777, link
            archive.addfile(item)
        return path, {'filename':path.name,'size':path.stat().st_size,'sha256':A.digest(path),'url':'https://example.invalid/unit-only'}

    def test_symlink_only_parent_exists_before_placeholder_creation(self):
        """! @brief 부모가 없는 원형 구조를 보존 기록하고 새 archive에서는 모든 부모를 먼저 생성합니다. """
        original, pin = self.upstream()
        first, second = self.root / 'one.tar.bz2', self.root / 'two.tar.bz2'
        record = A.normalize(original, first, {'LICENSE.txt':b'notice'}, pin)
        self.assertEqual(record['upstream_members_unchanged'], 3)
        self.assertFalse(record['executable_bytes_modified'])
        self.assertEqual(A.normalize(original, second, {'LICENSE.txt':b'notice'}, pin)['sha256'], record['sha256'])
        with tarfile.open(first) as archive:
            directories = set()
            for item in archive:
                if item.isdir():
                    directories.add(item.name)
                else:
                    self.assertIn(str(Path(item.name).parent).replace('\\','/'), directories)
            self.assertEqual(archive.extractfile('python/NU54_LICENSES/LICENSE.txt').read(), b'notice')
        observed = A.inventory(first)
        self.assertTrue(all(observed[name] == row for name,row in A.inventory(original).items()))

    def test_wrong_upstream_or_existing_output_is_never_reused(self):
        """! @brief 버전 문구가 같아도 입력 byte나 새 출력 조건이 다르면 실패합니다. """
        source, pin = self.upstream()
        target = self.root / 'result.tar.bz2'
        with self.assertRaises(ValueError):
            A.normalize(source, target, {}, dict(pin,sha256='0'*64))
        self.assertFalse(target.exists())
        target.write_bytes(b'preserved-failed-attempt')
        with self.assertRaises(ValueError):
            A.normalize(source, target, {}, pin)
        self.assertEqual(target.read_bytes(), b'preserved-failed-attempt')

    def test_symlink_escape_and_missing_target_are_rejected(self):
        """! @brief 누락·탈출 대상은 parent directory 추가로 정상처럼 꾸미지 않습니다. """
        for number, link in enumerate(('../../../../outside','../a/missing','/absolute')):
            case = self.root / str(number)
            case.mkdir()
            self.root = case
            source, pin = self.upstream(link)
            with self.assertRaises(ValueError):
                A.normalize(source, case / 'result.tar.bz2', {}, pin)

    def test_unsafe_member_names_are_rejected(self):
        """! @brief 경로 정규화가 archive root를 넘어가거나 다른 파일을 가리키지 못합니다. """
        for name in ('/python/a','python/../outside','python\\a','C:/python/a','other/a'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                A.safe_name(name)


if __name__ == '__main__':
    unittest.main()
