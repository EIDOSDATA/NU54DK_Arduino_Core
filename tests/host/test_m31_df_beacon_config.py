"""! @brief Direction Finding beacon의 periodic 광고 option 범위를 검사합니다. """

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "libraries/NUCODE_BLE_DirectionFinding/src/NUCODE_BLE_DirectionFinding.cpp"


class DirectionFindingBeaconConfigTest(unittest.TestCase):
    """! @brief 서로 다른 advertising option enum을 혼용하지 않도록 고정합니다. """

    def test_periodic_cte_does_not_request_unsupported_tx_power(self) -> None:
        """! @brief 고정 SDC가 거부하는 TX Power 속성을 CTE에 요청하지 않습니다. """
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn(
            "periodic_parameters.options = BT_LE_PER_ADV_OPT_NONE;",
            source,
        )
        self.assertNotIn(
            "periodic_parameters.options = BT_LE_ADV_OPT_USE_TX_POWER;",
            source,
        )
        self.assertNotIn(
            "periodic_parameters.options = BT_LE_PER_ADV_OPT_USE_TX_POWER;",
            source,
        )


if __name__ == "__main__":
    unittest.main()
