"""! @brief W07 초기 READY 이전 수신 경계와 READY 이후 strict parser를 실행 검증합니다. """
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
HIL = ROOT / "tests/hil/nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))
import m29_ble_signed_eatt as runner

REVISION = "1234567890abcdef1234567890abcdef12345678"


class BootPort:
    """! @brief boot record 관측 전에 query가 전송되면 즉시 거부합니다. """

    def __init__(self, role, boot=None):
        self.ready = f"{runner.PROTOCOL}|READY|role={role}|bond_count=0|core={REVISION}".encode()
        self.pending = bytearray((self.ready if boot is None else boot) + b"\r\n")
        self.boot_read = False
        self.writes = []

    @property
    def in_waiting(self):
        """! @brief 현재 반환 가능한 byte 수를 제공합니다. """
        return len(self.pending)

    def read(self, amount):
        """! @brief 최초 boot record와 후속 query 응답을 순서대로 반환합니다. """
        value = bytes(self.pending[:amount])
        del self.pending[:amount]
        if value:
            self.boot_read = True
        return value

    def reset_input_buffer(self):
        """! @brief boot READY를 검증하지 않고 지우는 경로를 검출합니다. """
        raise AssertionError("Boot READY must be observed before query")

    def write(self, value):
        """! @brief boot가 읽힌 뒤 exact query 한 번만 허용합니다. """
        if not self.boot_read:
            raise AssertionError("Query before boot READY")
        self.writes.append(value)
        self.pending.extend(self.ready + b"\r\n")
        return len(value)

    def flush(self):
        """! @brief 별도 동작 없이 flush 완료를 반환합니다. """
        return None


def extract_function(text, name):
    """! @brief 실제 target 함수의 전체 본문을 추출합니다. """
    match = re.search(r"(?m)^    (?:std::uint8_t|void|bool) " + name + r"\(", text)
    if match is None:
        raise AssertionError("Missing actual target function: " + name)
    start = text.index("{", match.start())
    depth = 0
    for position in range(start, len(text)):
        if text[position] == "{":
            depth += 1
        elif text[position] == "}":
            depth -= 1
            if depth == 0:
                return text[match.start():position + 1]
    raise AssertionError("Unterminated target function")


CPP_PREFIX = r"""
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <deque>
#include <string>
constexpr char ready_query[] = "M29W07|1|READY?";
constexpr char start_prefix[] = "M29W07|1|START|mode=";
constexpr char clear_prefix[] = "M29W07|1|CLEAR|nonce=";
constexpr char reboot_prefix[] = "M29W07|1|REBOOT|nonce=";
constexpr char signed_close_prefix[] = "M29W07|1|CLOSE|mode=sign|iteration=";
constexpr char core_suffix[] = "|core=1234567890abcdef1234567890abcdef12345678";
constexpr std::size_t nonce_text_length = 32U;
constexpr std::size_t nonce_binary_length = 16U;
enum class Mode : std::uint8_t
{
    idle,
    pair,
    sign,
    replay,
    eatt,
};
char command[192] = {};
std::size_t command_length = 0U;
char nonce[33] = {};
std::uint8_t nonce_binary[16] = {};
std::uint32_t iteration = 0U;
Mode mode = Mode::idle;
bool session_active = false;
std::string failure_stage;
unsigned clear_calls = 0U;
unsigned ready_calls = 0U;
struct SerialStub
{
    std::deque<unsigned char> bytes;
    int available()
    {
        return static_cast<int>(bytes.size());
    }
    int read()
    {
        if (bytes.empty())
        {
            return -1;
        }
        const int value = bytes.front();
        bytes.pop_front();
        return value;
    }
} Serial;
struct DeviceStub
{
    bool begin(const char *)
    {
        return true;
    }
    int lastDriverError()
    {
        return 0;
    }
} BLEDevice;
const char *roleName()
{
    return "central";
}
void fail(const char *stage, int = 0)
{
    failure_stage = stage;
}
void printReady()
{
    ++ready_calls;
}
void rebootTarget()
{
}
void closeSignedSession()
{
}
"""

CPP_HOOKS = r"""
void startSession()
{
    if (!acceptStartCommand())
    {
        fail("start_record");
        return;
    }
}
void clearBonds()
{
    if (!acceptNonceCommand(clear_prefix))
    {
        fail("clear_bonds");
        return;
    }
    ++clear_calls;
}
"""

CPP_MAIN = r"""
void resetState()
{
    std::memset(command, 0, sizeof(command));
    std::memset(nonce, 0, sizeof(nonce));
    command_length = 0U;
    mode = Mode::idle;
    session_active = false;
    failure_stage.clear();
    clear_calls = 0U;
    ready_calls = 0U;
    Serial.bytes.clear();
}
void feed(const std::string &value)
{
    for (unsigned char item : value)
    {
        Serial.bytes.push_back(item);
    }
    while (Serial.available() > 0)
    {
        pollHostCommand();
    }
}
int main()
{
    const std::string clear = "M29W07|1|CLEAR|nonce=0123456789abcdef0123456789abcdef|core=1234567890abcdef1234567890abcdef12345678\r\n";
    resetState();
    Serial.bytes.push_back(0xfe);
    setupTail();
    feed(clear);
    if (ready_calls != 1U || clear_calls != 1U || !failure_stage.empty())
    {
        return 1;
    }
    resetState();
    setupTail();
    feed(std::string(1, static_cast<char>(0xfe)) + clear);
    if (failure_stage != "start_record" || clear_calls != 0U || nonce[0] != '\0')
    {
        return 2;
    }
    resetState();
    Serial.bytes.assign(sizeof(command) + 1U, 0xfe);
    setupTail();
    if (ready_calls != 0U || failure_stage != "startup_rx_overflow")
    {
        return 3;
    }
    return 0;
}
"""


class M29SignedEattStartupTests(unittest.TestCase):
    """! @brief 실제 초기 명령 순서와 target parser의 거부 경계를 고정합니다. """

    def test_boot_ready_precedes_each_single_query(self):
        """! @brief 두 boot READY를 모두 읽은 뒤 exact query를 한 번씩 보냅니다. """
        ports = {role: BootPort(role) for role in ("peripheral", "central")}
        pending = {role: bytearray() for role in ports}
        captures = {role: bytearray() for role in ports}
        runner._query_ready(ports, pending, captures, REVISION, time.monotonic() + 1.0)
        for role, port in ports.items():
            self.assertEqual(port.writes, [(runner.PROTOCOL + "|READY?\r\n").encode()])
            self.assertEqual(bytes(captures[role]), (port.ready + b"\r\n") * 2)
            self.assertFalse(pending[role])

    def test_invalid_boot_record_blocks_all_queries(self):
        """! @brief boot FAIL·비 ASCII·다른 source를 버리지 않고 첫 단계에서 거부합니다. """
        good = BootPort("central").ready
        cases = (
            b"M29W07|1|FAIL|role=central|stage=device_begin",
            b"\xfe" + good,
            good.replace(REVISION.encode(), b"0" * 40),
        )
        for invalid in cases:
            with self.subTest(invalid=invalid):
                ports = {"peripheral": BootPort("peripheral"), "central": BootPort("central", invalid)}
                pending = {role: bytearray() for role in ports}
                captures = {role: bytearray() for role in ports}
                with self.assertRaises(runner.BlePairHilFailure):
                    runner._query_ready(ports, pending, captures, REVISION, time.monotonic() + 1.0)
                self.assertTrue(all(not port.writes for port in ports.values()))
                self.assertIn(invalid, captures["central"])

    def test_actual_target_boot_boundary_keeps_post_ready_rejection(self):
        """! @brief 실제 setup 후반·poll·dispatch·parser로 pre/post READY 차이를 검증합니다. """
        source = (ROOT / "tests/zephyr/m29_ble_signed_eatt_hil/src/main.cpp").read_text(encoding="utf-8")
        functions = {name: extract_function(source, name) for name in (
            "hexNibble", "buildNonceBinary", "acceptNonceCommand", "acceptStartCommand",
            "executeCommand", "pollHostCommand",
        )}
        boundary = ""
        if "bool prepareHostCommandBoundary()" in source:
            boundary = extract_function(source, "prepareHostCommandBoundary")
        setup = source[source.index("void setup()"):source.index("/** @brief Host command,")]
        tail = setup[setup.index("    if (!BLEDevice.begin(roleName()))"):setup.rfind("}")]
        code = CPP_PREFIX + "\n".join(functions[name] for name in (
            "hexNibble", "buildNonceBinary", "acceptNonceCommand", "acceptStartCommand",
        )) + CPP_HOOKS + "\n".join(functions[name] for name in (
            "executeCommand", "pollHostCommand",
        )) + boundary + "\nvoid setupTail()\n{\n" + tail + "\n}\n" + CPP_MAIN
        compiler = os.environ.get("CXX") or shutil.which("g++")
        self.assertIsNotNone(compiler, "C++ compiler required for actual UART parser test")
        with tempfile.TemporaryDirectory(prefix="m29-startup-") as temporary:
            directory = Path(temporary)
            cpp = directory / "startup.cpp"
            exe = directory / ("startup.exe" if os.name == "nt" else "startup")
            cpp.write_text(code, encoding="utf-8")
            built = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                                    str(cpp), "-o", str(exe)], capture_output=True, check=False)
            self.assertEqual(built.returncode, 0, built.stderr.decode(errors="replace"))
            result = subprocess.run([str(exe)], capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, "Actual target startup boundary case failed")


if __name__ == "__main__":
    unittest.main()
