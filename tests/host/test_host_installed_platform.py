"""! @brief 실제 Host에서 공백·한글 설치 root의 동일 byte 빌드 복사본과 경계를 검사합니다. """
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('portable_installed_platform_unit',ROOT/'tools/nu54-builder/src/nu54_builder.py')
B=importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)
P=B.implementation.installed_platform


class InstalledPlatformTests(unittest.TestCase):
    """! @brief Source identity는 원본으로 유지하고 실제 compile 입력만 안전한 복사본으로 연결합니다. """

    def setUp(self):
        """! @brief SDK 밖의 독립 임시 설치본을 생성합니다. """
        self.temporary=tempfile.TemporaryDirectory(prefix='native-installed-platform-')
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name).resolve()
        self.installed=self.root/'한글 설치 공백'
        self.installed.mkdir()
        (self.installed/'release-manifest.json').write_bytes(b'{}\n')
        self.source=self.installed/'libraries/Test/src/Test.cpp'
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b'int native_value = 54;\n')
        self.paths={'platform_root':self.installed,'workspace':self.root/'cache'}

    def test_native_copy_maps_same_bytes_and_preserves_logical_original(self):
        """! @brief POSIX도 unquoted SDK module env의 공백 분할을 피하며 원본 metadata를 유지합니다. """
        self.assertTrue(P.requires_platform_copy(self.installed))
        P.materialize_installed_platform(self.paths)
        shadow=P.platform_build_root(self.paths)
        self.assertEqual(shadow,self.paths['workspace']/'platform')
        compiled=P.platform_compiled_path(self.source,self.paths)
        self.assertEqual(compiled.read_bytes(),self.source.read_bytes())
        self.assertEqual(self.paths['platform_root'],self.installed)
        expected={'platform_build_copy':{'content':B.tree_content_sha256(self.installed,('.',))}}
        P.validate_platform_copy(self.paths,expected)
        compiled.write_bytes(b'corrupted')
        with self.assertRaisesRegex(B.AdapterError,'E_PLATFORM_COPY_STALE'):
            P.validate_platform_copy(self.paths,expected)
        P.materialize_installed_platform(self.paths)
        P.validate_platform_copy(self.paths,expected)

    def test_checkout_and_external_sources_keep_identity_and_bad_cache_fails(self):
        """! @brief Git checkout·외부 library를 설치 복사본으로 바꾸거나 unsafe cache를 허용하지 않습니다. """
        (self.installed/'.git').mkdir()
        self.assertFalse(P.requires_platform_copy(self.installed))
        (self.installed/'.git').rmdir()
        external=self.root/'external.cpp'
        self.assertEqual(P.platform_compiled_path(external,self.paths),external)
        with self.assertRaisesRegex(B.AdapterError,'E_SDK_BUILD_PATH'):
            P.platform_build_root(dict(self.paths,workspace=self.root/'cache space'))


if __name__=='__main__':
    unittest.main()
