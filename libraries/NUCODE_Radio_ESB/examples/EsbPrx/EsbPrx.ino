/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * ESB PRX 수신 sequence/hash/중복과 ACK payload를 확인하는 예제입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standalone Enhanced ShockBurst radio (`radio_esb`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) ESB PRX; 2) ESB PTX
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 두 보드의 channel, bitrate, pipe를 같게 설정하고 PRX를 먼저 시작합니다.
 * @par 준비물
 * - NU54DK 보드 2대 — 1) ESB PRX; 2) ESB PTX
 * - 두 보드의 channel, bitrate, pipe를 같게 설정하고 PRX를 먼저 시작합니다.
 * @par 설정
 * - Tools → Feature set에서 `radio_esb` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `ESB PRX ready`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `sequence=`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `hash=`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `ESB PRX start failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_Radio_ESB/EsbPtx`
 * @par 종료와 재시작
 * - 예제의 stop/end/disconnect 또는 유한 완료 흐름 뒤 오류와 자원 반환을 확인합니다.
 * - 실패 문구와 driver 상태를 확인한 뒤 명시적 reset 또는 예제의 재시작 흐름을 사용합니다.
 * @par 보안
 * - wireless_example_no_implicit_security_claim
 * - 무선 연결 성공만으로 인증·암호화·상호운용 보안을 주장하지 않습니다.
 * @par 제한
 * - Compile·Host 검사는 실제 보드 runtime 또는 외부 제품 상호운용 PASS를 대신하지 않습니다.
 * - 목적과 metadata 조건 밖의 성능·동시성·정밀도는 이 예제의 보증 범위가 아닙니다.
 * @par Negative
 * - wrong_profile_or_missing_sidecar
 * - missing_or_wrong_role_peer
 * - startup_or_runtime_error_reported
 * @par Traceability
 * Recipe `radio_esb`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_Radio_ESB/EsbPrx`, sha256 `b72f2bda0820d7bd730f3316a4c63fec5accf0470d8b12d27c41b732da35cf34`
 * @nucode_example_setup_end */

/**
 * @file EsbPrx.ino
 * @brief ESB PRX 수신 sequence/hash/중복과 ACK payload를 확인하는 예제입니다.
 */

#include <NUCODE_Radio_ESB.h>

void setup()
{
    Serial.begin(115200);
    nucode::esb::Configuration configuration{};
    configuration.channel = 40U;
    configuration.bitrate = nucode::esb::Bitrate::mbps2;
    if (!NUCODEEsb.begin(nucode::esb::Role::primary_receiver, configuration))
    {
        Serial.println("ESB PRX start failed");
        return;
    }
    static const std::uint8_t ack_payload[] = {'A', 'C', 'K'};
    static_cast<void>(NUCODEEsb.send(0U, ack_payload, sizeof(ack_payload)));
    Serial.println("ESB PRX ready");
}

void loop()
{
    nucode::esb::Packet packet{};
    while (NUCODEEsb.read(packet))
    {
        Serial.print("sequence=");
        Serial.print(packet.sequence);
        Serial.print(" hash=");
        Serial.print(packet.hash_valid ? "ok" : "bad");
        Serial.print(" duplicate=");
        Serial.println(packet.duplicate ? "yes" : "no");
        static const std::uint8_t ack_payload[] = {'A', 'C', 'K'};
        static_cast<void>(NUCODEEsb.send(packet.sequence, ack_payload, sizeof(ack_payload)));
    }
    delay(5);
}
