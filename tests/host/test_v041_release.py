"""! @brief v0.4.1 유지보수 릴리스 도구의 fail-closed 계약을 검증합니다. """

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


def load(name, relative):
    """! @brief 지정 저장소 모듈을 격리 이름으로 로드합니다. """
    specification = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


RELEASE = load("test_v041_release_module", "tools/release/v041_release.py")


class V041ReleaseTests(unittest.TestCase):
    """! @brief v0.4.1 전용 version·catalog·자산 검증을 고정합니다. """

    def test_contract_is_separate_and_single_version(self):
        """! @brief 공개 쓰기 없는 명령과 단일 지원 version을 확인합니다. """
        choices = set(RELEASE.build_parser()._subparsers._group_actions[0].choices)
        self.assertEqual(choices, {"contract", "prepare", "validate-plan", "verify-public"})
        self.assertEqual(RELEASE.VERSION, "0.4.1")
        self.assertEqual(RELEASE.TAG, "v0.4.1")
        self.assertNotIn("publish-release", choices)
        self.assertNotIn("publish-index", choices)

    def test_unpublished_stable_configuration_is_process_local(self):
        """! @brief v0.4.1 후보 구성 후 새 모듈에는 변경이 남지 않는지 확인합니다. """
        package = load("test_v041_package_configured", "packaging/boards-manager/nu54_package.py")
        self.assertNotIn(RELEASE.VERSION, package.STABLE_VERSIONS)
        RELEASE.configure_package(package, "1" * 40)
        self.assertIn(RELEASE.VERSION, package.STABLE_VERSIONS)
        self.assertEqual(package.STABLE_RELEASE_COMMITS[RELEASE.VERSION], "1" * 40)

        fresh = load("test_v041_package_fresh", "packaging/boards-manager/nu54_package.py")
        self.assertNotIn(RELEASE.VERSION, fresh.STABLE_VERSIONS)

    def test_release_documents_are_complete(self):
        """! @brief 공개 사용자 문서 5종과 별도 안내 문서가 모두 있는지 확인합니다. """
        self.assertEqual(len(RELEASE.DOCUMENT_PATHS), 5)
        for relative in RELEASE.DOCUMENT_PATHS.values():
            self.assertTrue((ROOT / relative).is_file(), relative)
        self.assertTrue((ROOT / "00_Docs/05_릴리스/v0.4.1/README.md").is_file())

    def test_plan_rejects_multiple_catalog_versions(self):
        """! @brief plan이 과거 version을 stable catalog에 섞으면 거부하는지 확인합니다. """
        with tempfile.TemporaryDirectory(prefix="nu54-v041-plan-") as folder:
            plan = Path(folder) / RELEASE.PLAN_FILENAME
            plan.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "v0.4.1-maintenance-release-plan",
                        "version": "0.4.1",
                        "release_tag": "v0.4.1",
                        "target_commit": "1" * 40,
                        "supported_catalog_versions": ["0.4.1", "0.4.0"],
                        "release_upload_roles": list(
                            RELEASE.PACKAGE_ROLES + tuple(RELEASE.DOCUMENT_PATHS)
                        ),
                        "artifacts": {},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RELEASE.ReleaseFailure, "plan 계약"):
                RELEASE.validate_plan(plan)


if __name__ == "__main__":
    unittest.main()
