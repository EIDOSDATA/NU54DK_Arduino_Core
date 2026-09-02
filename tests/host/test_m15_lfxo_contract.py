"""! @brief NU54DK 외부 LFXO 부하 커패시터 override의 단일 원본 계약을 검증합니다. """

from __future__ import annotations

from pathlib import Path
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
FRAGMENT = REPOSITORY / "dts" / "nucode" / "nu54dk-lfxo-external-caps.dtsi"
INCLUDE = "#include <nucode/nu54dk-lfxo-external-caps.dtsi>"
CONSUMERS = (
    REPOSITORY / "tools" / "nu54-builder" / "templates" / "zephyr-app" / "app.overlay",
    REPOSITORY / "tests" / "zephyr" / "m15_board" / "app.overlay",
    REPOSITORY / "tests" / "zephyr" / "m15_hil" / "app.overlay",
    REPOSITORY / "tests" / "zephyr" / "m15_wake" / "app.overlay",
)


class M15LfxoContractTests(unittest.TestCase):
    """! @brief 회로와 일치하는 LFXO override가 중복 없이 소비되는지 검사합니다. """

    def test_shared_fragment_uses_only_external_load_capacitors(self) -> None:
        """! @brief 외부 커패시터 선택과 내부 커패시터 속성 삭제를 고정합니다. """
        source = FRAGMENT.read_text(encoding="utf-8")
        self.assertEqual(source.count("&lfxo"), 1)
        self.assertEqual(source.count('load-capacitors = "external";'), 1)
        self.assertEqual(
            source.count("/delete-property/ load-capacitance-femtofarad;"), 1
        )
        self.assertNotIn("external-clock-source", source)

    def test_all_arduino_and_m15_builds_include_the_shared_fragment(self) -> None:
        """! @brief 모든 Arduino 빌드와 M15 image가 같은 DTSI를 사용하도록 고정합니다. """
        for path in CONSUMERS:
            with self.subTest(path=path.relative_to(REPOSITORY).as_posix()):
                source = path.read_text(encoding="utf-8")
                self.assertEqual(source.count(INCLUDE), 1)
                self.assertNotIn("&lfxo", source)

    def test_profile_and_library_feature_do_not_duplicate_board_override(self) -> None:
        """! @brief profile 추가나 library 선택에 따라 LFXO 설정이 달라지지 않게 합니다. """
        for path in (
            REPOSITORY / "variants" / "nu54dk" / "profiles" / "standard" / "app.overlay",
            REPOSITORY / "libraries" / "NUCODE_NU54DK" / "zephyr" / "board-system.overlay",
        ):
            with self.subTest(path=path.relative_to(REPOSITORY).as_posix()):
                source = path.read_text(encoding="utf-8")
                self.assertNotIn("&lfxo", source)
                self.assertNotIn(INCLUDE, source)


if __name__ == "__main__":
    unittest.main()
