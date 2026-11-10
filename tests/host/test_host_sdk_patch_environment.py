"""! @brief 시스템 PATH 없이 명시한 Git으로 patch 적용·복원이 실제 가능한지 검사합니다. """
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('sdk_patch_environment_unit', ROOT/'tools/nu54-builder/src/nu54_builder_impl/sdk_patches.py')
M=importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


class SdkPatchEnvironmentTests(unittest.TestCase):
    """! @brief 제품 SDK 대신 독립 임시 Git fixture만 수정합니다. """

    def setUp(self):
        """! @brief 테스트 harness의 Git 절대 경로와 새 fixture를 준비합니다. """
        binary=shutil.which('git')
        if binary is None:
            self.skipTest('임시 Git fixture를 만들 harness Git이 없습니다.')
        self.git=Path(binary).absolute()
        self.temporary=tempfile.TemporaryDirectory(prefix='sdk-patch-environment-unit-')
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name).resolve()
        self.zephyr=self.root/'zephyr'
        self.zephyr.mkdir()
        subprocess.check_call([str(self.git),'init','--quiet',str(self.zephyr)])
        self.invoke('config','core.autocrlf','false')
        self.invoke('config','core.hooksPath',str(self.root/'no-hooks'))
        (self.zephyr/'example.txt').write_bytes(b'before\n')
        self.invoke('add','example.txt')
        self.invoke('-c','user.name=Unit Fixture','-c','user.email=unit@example.invalid',
            '-c','commit.gpgsign=false','commit','--quiet','-m','fixture')
        self.lock={'zephyr':{'revision':self.invoke('rev-parse','HEAD').strip()}}
        patch=self.root/'fixture.patch'
        patch.write_bytes(b'diff --git a/example.txt b/example.txt\n--- a/example.txt\n+++ b/example.txt\n@@ -1 +1 @@\n-before\n+after\n')
        self.record={'path':'fixture.patch','files':['example.txt']}
        self.empty=self.root/'empty-path'
        self.empty.mkdir()
        self.environment=dict(os.environ,PATH=str(self.empty),NUCODE_SDK_GIT=str(self.git))

    def invoke(self,*arguments):
        """! @brief 초기 fixture Git만 절대 경로로 실행합니다. """
        return subprocess.check_output([str(self.git),'-C',str(self.zephyr),*arguments],text=True,encoding='utf-8')

    def test_apply_and_restore_use_explicit_git_without_parent_PATH(self):
        """! @brief 적용·변경 확인·역적용·최종 clean 모두 같은 명시 경로를 사용합니다. """
        previous=os.environ.get('PATH')
        with mock.patch.object(M,'REPOSITORY',self.root), mock.patch.object(M,'approved_zephyr_patches',return_value=(self.record,)):
            with M.applied_zephyr_patches(self.root,self.lock,environment=self.environment):
                self.assertEqual((self.zephyr/'example.txt').read_bytes(),b'after\n')
        self.assertEqual((self.zephyr/'example.txt').read_bytes(),b'before\n')
        self.assertEqual(M._content_changes(self.zephyr,environment=self.environment),())
        self.assertEqual(os.environ.get('PATH'),previous)

    def test_build_exception_still_restores_with_the_same_git(self):
        """! @brief 실제 build 실패를 모사해도 다른 PATH를 사용하거나 patch를 남기지 않습니다. """
        with mock.patch.object(M,'REPOSITORY',self.root), mock.patch.object(M,'approved_zephyr_patches',return_value=(self.record,)):
            with self.assertRaisesRegex(RuntimeError,'unit build failure'):
                with M.applied_zephyr_patches(self.root,self.lock,environment=self.environment):
                    raise RuntimeError('unit build failure')
        self.assertEqual((self.zephyr/'example.txt').read_bytes(),b'before\n')
        self.assertEqual(M._content_changes(self.zephyr,environment=self.environment),())

    def test_missing_relative_or_nonexistent_sdk_git_never_falls_back(self):
        """! @brief PATH에 Git이 있어도 명시한 SDK Git이 잘못됐으면 즉시 실패합니다. """
        for value in (None,'git',str(self.root/'missing-git')):
            environment=dict(os.environ)
            if value is not None:
                environment['NUCODE_SDK_GIT']=value
            else:
                environment.pop('NUCODE_SDK_GIT',None)
            with self.subTest(value=value), self.assertRaises(M.PatchFailure):
                M._git(self.zephyr,('rev-parse','HEAD'),environment=environment)


if __name__=='__main__':
    unittest.main()
