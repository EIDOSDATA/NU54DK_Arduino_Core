# NU54DK Arduino Core v0.5.0

`v0.5.0`은 Windows 10/11 x64와 Arduino IDE 2.x/Arduino CLI를 지원하는 정식 릴리스입니다.
M28~M31의 확장 Bluetooth 기능, 113개 공개 예제, 업로드 진단과 증분 빌드 교정을 포함합니다.

## Arduino IDE 설치

1. `File → Preferences → Additional Boards Manager URLs`에 아래 URL을 추가합니다.
2. Boards Manager에서 `NUCODE NU54DK Zephyr Boards`를 찾습니다.
3. **0.5.0**을 선택해 설치하고 post-install 실행을 승인합니다.
4. `Nordic prerequisite installation PASS`를 확인합니다.

[Boards Manager stable index](https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json):

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

보드는 `NU54DK (nRF54L15, Zephyr)`, 기본 Feature set은 `Standard peripherals`입니다.
온보드 probe가 한 대면 `CMSIS-DAP - one probe auto (multiple: CLI UID)`를 선택합니다.
`File → Examples → NUCODE NU54DK → Blink`에서 Verify와 Upload를 실행해 시작할 수 있습니다.

첫 설치는 NCS v3.4.0과 고정 toolchain을 내려받으므로 시간이 걸릴 수 있습니다. 별도 Git, Python,
nRF Connect for Desktop 또는 VS Code 설치는 필수가 아닙니다. Serial 예제는 대응 DAP UART COM 포트를
115200 8N1로 엽니다. COM 포트 선택과 SWD probe 선택은 서로 다릅니다.

## Feature set과 예제

| Feature set | 용도 |
| --- | --- |
| `Standard peripherals` | 일반 Arduino API, Storage, 기본 BLE와 기본 예제 |
| `BLE NUS` | NUS와 일반 확장 BLE 예제의 권장 구성 |
| `Adaptive capabilities (experimental)` | 예제 선언에 따른 최소 기능 구성; 실험적 대안 |
| `Peripheral Fabric (DAP UART disconnected)` | 인스턴스별 DMA와 주변장치 직접 제어 |
| `Secure BLE DFU (MCUboot)` | 서명된 BLE DFU 전용 구성 |
| `BLE Audio external I/O (DAP UART disconnected)` | 외장 Audio I/O 전용 구성 |

113개 `.ino` 상단에는 권장 Feature set, 허용 대안, 보드 수와 역할, Serial, sidecar와 결선 조건이
표시됩니다. `nucode-build.json`, `prj.conf`, overlay는 예제 폴더와 함께 유지해야 합니다.

## 배포 identity와 지원 경계

| 항목 | 값 |
| --- | --- |
| Release | [v0.5.0](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.5.0) |
| 보드 | NU54DK nRF54L15 CPUAPP |
| Host | Windows 10/11 x64 |
| SDK | NCS v3.4.0 / Zephyr 4.4.0 / 고정 toolchain |
| Board source | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 패키지 | 16개 library, 113개 예제 |

제품 SDC의 DF IQ RX와 AoD는 지원하지 않습니다. Adaptive와 EATT는 experimental opt-in이고 Signed
Write는 legacy opt-in입니다. Ubuntu/macOS 설치, 외장 audio 장치, 상용 BLE peer, 정밀 RF·음질·거리·
각도 보정과 모든 기능 동시 조합은 검증 보증 범위 밖입니다.

[변경점](RELEASE_NOTES.md) · [이전 버전에서 이동](MIGRATION.md) · [검증 범위](TESTING.md) ·
[알려진 제한](KNOWN_ISSUES.md) · [문제 해결](TROUBLESHOOTING.md)
