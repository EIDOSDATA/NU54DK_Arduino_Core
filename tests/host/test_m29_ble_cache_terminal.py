"""! @brief 실제 cache target의 종료 함수와 loop를 컴파일해 반복 출력과 FAIL 뒤 PASS를 거부합니다. """

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from ble_source_contracts import function_body
from host_compiler import compiler_command, run_executable


ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "tests/zephyr/m29_ble_cache_hil/src/main.cpp"


HARNESS_PREFIX = r"""
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <sstream>
#include <string>

#define NUCODE_M29_CACHE_CENTRAL 1
#define M29_CACHE_CORE_REVISION "0123456789abcdef0123456789abcdef01234567"

/** @brief UART 출력은 실제 함수에서 생성한 byte 순서대로 메모리에 보존합니다. */
struct SerialFixture
{
    std::ostringstream output;

    template <typename T>
    void print(const T &value)
    {
        output << value;
    }

    void println()
    {
        output << "\n";
    }
};

SerialFixture Serial;
constexpr char protocol[] = "M29W05|1";
constexpr char nonce[] = "00112233445566778899aabbccddeeff";
constexpr char resume_key[] = "fixture/resume";
bool protocol_started = true;
bool protocol_finished = false;
bool scan_pending = false;
bool callback_context_valid = true;
std::int64_t protocol_deadline = 1;
int connection_handle = 1;
std::uint16_t reconnects = 20;
std::uint16_t hash_reads = 24;
std::uint16_t cache_saves = 4;
std::uint16_t cache_restores = 20;
std::uint16_t cache_invalidations = 2;
std::uint16_t service_changed_events = 1;
unsigned delete_calls = 0;
unsigned statistic_calls = 0;
unsigned poll_calls = 0;
unsigned host_poll_calls = 0;
unsigned security_calls = 0;
unsigned delay_calls = 0;
bool client_busy = false;
bool failure_during_poll = false;

namespace nucode::ble
{
    struct BLEGattCacheStatistics
    {
        unsigned corrupt_rejected = 1;
    };
}

/** @brief SDK·BLE 의존성만 대체하며 종료 조건과 출력 함수는 target 원문을 사용합니다. */
struct ClientFixture
{
    bool busy(int)
    {
        return client_busy;
    }

    nucode::ble::BLEGattCacheStatistics cacheStatistics()
    {
        ++statistic_calls;
        return {};
    }
};

ClientFixture BLEClient;

void fail(const char *stage, int code, int ble_error);

struct DeviceFixture
{
    void poll()
    {
        ++poll_calls;
        if (failure_during_poll && poll_calls == 1U)
        {
            fail("fixture_gap_error", -1, -1);
        }
    }
};

DeviceFixture BLEDevice;

int settings_delete(const char *)
{
    ++delete_calls;
    return 0;
}

void pollHostCommand()
{
    ++host_poll_calls;
}

void startScan()
{
    scan_pending = false;
}

void driveSecurity()
{
    ++security_calls;
}

std::int64_t k_uptime_get()
{
    return 0;
}

void delay(unsigned)
{
    ++delay_calls;
}
"""


HARNESS_SUFFIX = r"""
/** @brief 실제 UART 기록에서 record 종류별 발생 횟수를 셉니다. */
std::size_t countRecords(const std::string &text, const std::string &token)
{
    std::size_t count = 0U;
    std::size_t position = 0U;
    while ((position = text.find(token, position)) != std::string::npos)
    {
        ++count;
        position += token.size();
    }
    return count;
}

/** @brief 각 독립 프로세스에서 실제 loop를 반복하고 관측만 출력합니다. */
int main(int argc, char **argv)
{
    if (argc != 2)
    {
        return 2;
    }

    const std::string scenario = argv[1];
    central_stage = CentralStage::finishing;
    if (scenario == "already_finished")
    {
        protocol_finished = true;
    }
    else if (scenario == "after_failure")
    {
        fail("fixture_prior_failure");
    }
    else if (scenario == "failure_during_poll")
    {
        failure_during_poll = true;
    }
    else if (scenario == "busy_then_idle")
    {
        client_busy = true;
    }
    else if (scenario == "unfinished_idle")
    {
        central_stage = CentralStage::idle;
    }
    else if (scenario != "finishing_repeated")
    {
        return 2;
    }

    for (unsigned index = 0U; index < 100U; ++index)
    {
        loop();
    }

    const std::size_t before_idle_results =
        countRecords(Serial.output.str(), "|RESULT|role=central|");
    if (scenario == "busy_then_idle")
    {
        client_busy = false;
        for (unsigned index = 0U; index < 100U; ++index)
        {
            loop();
        }
    }

    const std::string uart = Serial.output.str();
    std::cout << "{\"results\":" << countRecords(uart, "|RESULT|role=central|")
              << ",\"ends\":" << countRecords(uart, "|END|role=central|")
              << ",\"failures\":" << countRecords(uart, "|FAIL|role=central|")
              << ",\"deletes\":" << delete_calls
              << ",\"statistics\":" << statistic_calls
              << ",\"polls\":" << poll_calls
              << ",\"host_polls\":" << host_poll_calls
              << ",\"security_calls\":" << security_calls
              << ",\"delays\":" << delay_calls
              << ",\"finished\":" << (protocol_finished ? "true" : "false")
              << ",\"before_idle_results\":" << before_idle_results
              << "}\n";
    return 0;
}
"""


class M29CacheTerminalTests(unittest.TestCase):
    """! @brief 실제 finite 종료 경계의 반복과 첫 실패 보존을 검증합니다. """

    @classmethod
    def setUpClass(cls) -> None:
        """! @brief 기존 brace 추출 helper로 target 함수를 그대로 결합해 한 번 컴파일합니다. """

        target = TARGET.read_text(encoding="utf-8")
        functions = [
            function_body(target, "const char *roleName()"),
            function_body(target, "void printSuffix()"),
            function_body(target, "void fail(const char *stage"),
            function_body(target, "void printCentralResult()"),
            function_body(target, "void loop()"),
        ]
        stage = function_body(target, "enum class CentralStage : std::uint8_t") + ";\n"
        stage += "CentralStage central_stage = CentralStage::idle;\n"
        cls.temporary = tempfile.TemporaryDirectory(prefix="nu54-m29-cache-terminal-")
        cls.addClassCleanup(cls.temporary.cleanup)
        folder = Path(cls.temporary.name)
        harness = folder / "cache_terminal.cpp"
        harness.write_text(
            HARNESS_PREFIX + stage + "\n".join(functions) + HARNESS_SUFFIX,
            encoding="utf-8",
        )
        cls.binary = folder / "cache_terminal.exe"
        command = [
            *compiler_command(), "-std=c++17", "-Wall", "-Wextra", "-Werror",
            str(harness), "-o", str(cls.binary),
        ]
        result = subprocess.run(command, capture_output=True, timeout=60)
        if result.returncode != 0:
            raise AssertionError(result.stderr.decode("utf-8", errors="replace"))

    def observe(self, scenario: str) -> dict[str, object]:
        """! @brief 원형 loop의 관측 JSON을 읽으며 C++ NDEBUG와 무관한 assertion을 사용합니다. """

        result = run_executable(
            [str(self.binary), scenario], capture_output=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
        return json.loads(result.stdout)

    def assert_observation(
        self, scenario: str, *, results: int, failures: int, polls: int,
        finished: bool, before_idle_results: int,
    ) -> None:
        """! @brief 종료 출력·영속 삭제·poll 횟수를 함께 검사합니다. """

        actual = self.observe(scenario)
        self.assertEqual(actual, {
            "results": results,
            "ends": results,
            "failures": failures,
            "deletes": results,
            "statistics": results,
            "polls": polls,
            "host_polls": polls,
            "security_calls": polls,
            "delays": polls,
            "finished": finished,
            "before_idle_results": before_idle_results,
        })

    def test_finishing_repeated_loop_prints_and_deletes_once(self) -> None:
        """! @brief 완료 뒤 100회 loop에도 RESULT·END·resume 삭제가 각각 한 번입니다. """

        self.assert_observation(
            "finishing_repeated", results=1, failures=0, polls=100,
            finished=True, before_idle_results=1,
        )

    def test_already_finished_has_no_terminal_side_effect(self) -> None:
        """! @brief 이미 완료된 상태에서는 출력과 Settings 변경을 다시 하지 않습니다. """

        self.assert_observation(
            "already_finished", results=0, failures=0, polls=100,
            finished=True, before_idle_results=0,
        )

    def test_prior_failure_never_prints_success(self) -> None:
        """! @brief 실제 fail() 뒤 finishing 상태여도 PASS·END를 출력하지 않습니다. """

        self.assert_observation(
            "after_failure", results=0, failures=1, polls=100,
            finished=True, before_idle_results=0,
        )

    def test_failure_during_ble_poll_prevents_success(self) -> None:
        """! @brief 같은 loop의 BLE poll에서 먼저 실패하면 완료 성공 출력을 차단합니다. """

        self.assert_observation(
            "failure_during_poll", results=0, failures=1, polls=100,
            finished=True, before_idle_results=0,
        )

    def test_busy_then_idle_prints_only_after_operation_finishes(self) -> None:
        """! @brief ATT 작업 중 100회에는 출력이 없고 해제 후 한 번만 종료합니다. """

        self.assert_observation(
            "busy_then_idle", results=1, failures=0, polls=200,
            finished=True, before_idle_results=0,
        )

    def test_unfinished_idle_remains_without_success(self) -> None:
        """! @brief 시작 전 idle 단계는 poll을 계속해도 종료 성공으로 바뀌지 않습니다. """

        self.assert_observation(
            "unfinished_idle", results=0, failures=0, polls=100,
            finished=False, before_idle_results=0,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
