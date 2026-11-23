# Arduino IDE에서 첫 예제 실행하기

NU54DK 한 대와 데이터 통신용 USB 케이블로 시작합니다. LED로 업로드를 확인하고, 같은 보드로 직렬 통신을 해 본 다음, 두 번째 보드가 있으면 BLE로 짧은 메시지를 보내 보세요. 처음 설치하는 경우 먼저 [Boards Manager 설치 안내](README.md)를 따릅니다.

## 1. Blink로 업로드 확인하기

1. 보드 한 대를 연결하고 `Tools > Board`에서 **NU54DK (nRF54L15, Zephyr)**를 선택합니다. `Tools > Port`에서는 방금 연결한 보드의 포트를 고릅니다. 연결 전후 포트 목록을 비교하면 이 보드의 포트를 찾을 수 있습니다. 보드 한 대가 가상 직렬 포트 두 개로 나타날 수 있습니다.
2. `Tools > Feature set > Standard peripherals`를 선택합니다. `Tools > Upload probe`는 기본값 **CMSIS-DAP - one probe auto (multiple: CLI UID)**를 사용합니다. Port는 직렬 통신 대상을 고르는 메뉴입니다. IDE 기본 업로드에서는 대상 보드 한 대만 연결해 프로브가 하나만 보이게 하세요.
3. `File > Examples > NUCODE NU54DK > Blink`를 엽니다. **Verify**로 컴파일한 뒤 **Upload**를 누릅니다. IDE 출력 창에 `Done uploading.`이 나오면 보드의 초록색 LED를 보세요.

스케치의 `setup()`은 시작할 때 한 번 실행되어 `LED_BUILTIN`을 출력으로 설정합니다. 이후 `loop()`가 아래 네 줄을 반복합니다. `writeBuiltinLed()`는 같은 스케치 아래쪽에서 `digitalWrite()`로 내장 LED 핀을 제어합니다. [Blink 전체 코드](../../../libraries/NUCODE_NU54DK/examples/Blink/Blink.ino)

```cpp
writeBuiltinLed(true);
delay(250);
writeBuiltinLed(false);
delay(250);
```

LED는 0.25초 켜지고 0.25초 꺼집니다. 내 코드가 올라갔는지 눈으로 확인하려면 스케치를 스케치북에 다른 이름으로 저장하고 두 `250`을 모두 `500`으로 바꿔 다시 Upload하세요. 한 번 켜졌다 꺼지는 주기가 약 1초가 됩니다.

## 2. SerialEcho로 한 줄 주고받기

1. 같은 보드와 Feature set에서 `File > Examples > NUCODE NU54DK > SerialEcho`를 열고 **Upload**합니다.
2. 보드의 DAP UART 스위치를 콘솔에 연결한 상태에서 P1 쪽 콘솔(uart20) 포트를 선택합니다. `Tools > Serial Monitor`를 열고 속도 **115200 baud**, 줄 끝 **Newline**을 고릅니다. 입력 칸에 `test`를 적고 전송합니다.
3. 같은 모니터에 **`NUCODE_M6_ECHO:test`**가 돌아오는지 확인합니다. 포트가 두 개인데 응답이 없으면 다른 포트를 선택해 다시 보내세요. 응답이 오는 쪽이 이 보드의 콘솔입니다. 시작할 때 출력하는 `NUCODE_M6_SERIAL_READY`를 놓쳤더라도 새 줄을 보내 통신을 확인할 수 있습니다.

`loop()`는 `Serial.available()`로 읽을 데이터가 있는지 확인하고 한 바이트씩 모읍니다. 줄바꿈 문자 `\n`을 받으면 다음 두 줄로 응답합니다. **No line ending**을 선택하면 보드가 줄 끝을 기다립니다. 한 줄의 입력 한도는 127바이트입니다. [SerialEcho 전체 코드](../../../libraries/NUCODE_NU54DK/examples/SerialEcho/SerialEcho.ino)

```cpp
Serial.print("NUCODE_M6_ECHO:");
Serial.println(line_buffer);
```

공개 v0.6.0에서 SerialEcho, AnalogReadA0, SPITransaction, WirePmicId의 첫 주석에는 직렬 모니터를 사용하지 않는다고 적혀 있습니다. 네 예제 모두 실제 코드는 `Serial.begin(115200U)`로 시작합니다. 출력을 읽을 때 **115200 baud**를 선택하세요.

## 3. 보드 두 대로 BLE 메시지 보내기

두 보드 모두 `Tools > Feature set > BLE NUS`를 선택합니다. 예제를 열 때마다 해당 IDE 창의 보드와 메뉴 값을 확인하세요. 각 보드에는 서로 다른 스케치를 올립니다.

| 보드 | IDE에서 열 예제 | 시작할 때 하는 일 |
| --- | --- | --- |
| A | `File > Examples > NUCODE BLE > NUSPeripheral` | `beginPeripheral("NU54-NUS")`로 이름을 지정하고 `startAdvertising()`으로 자신을 알립니다. [전체 코드](../../../libraries/NUCODE_BLE/examples/NUSPeripheral/NUSPeripheral.ino) |
| B | `File > Examples > NUCODE BLE > NUSCentral` | `beginCentral()`로 검색할 준비를 하고 `scanForNus("NU54-NUS")`로 A를 찾습니다. [전체 코드](../../../libraries/NUCODE_BLE/examples/NUSCentral/NUSCentral.ino) |

1. A만 연결해서 Peripheral 스케치를 업로드하고 A를 분리합니다. B만 연결해서 Central을 업로드합니다. 이제 두 보드를 모두 연결해 전원을 공급합니다.
2. IDE 창 두 개에서 각각 A와 B의 콘솔 포트를 선택하고 직렬 모니터를 **115200 baud**로 엽니다. Peripheral은 준비되면 `BLE NUS ready`를 출력합니다.
3. A의 모니터에서 `hello`를 보내고 **B의 모니터**에서 읽습니다. B에서 `reply`를 보내면 A에서 읽을 수 있습니다.

두 스케치의 `loop()`는 `BLESerial.poll()`로 연결과 수신 이벤트를 처리합니다. BLE에서 읽은 바이트는 로컬 직렬 포트에 쓰고, 직렬 입력은 `BLESerial.ready()`가 참일 때 상대 보드로 보냅니다. 이름을 바꿨다면 A의 광고 이름과 B의 검색 이름을 맞추세요.

## 다음 예제 고르기

- 특정 기능을 써 보고 싶다면 메뉴 이름별로 권장 스케치와 준비물을 찾으세요. [Feature set 12개 안내](FEATURE_SETS.md)
- Mesh, 센서, 오디오 같은 역할별 예제를 찾으려면 시나리오 또는 라이브러리 이름으로 찾아보세요. 스케치를 복사할 때는 같은 폴더의 `nucode-build.json`, `prj.conf`, `app.overlay`도 함께 복사하세요. [전체 예제 색인](../../../libraries/EXAMPLES.md)
- 업로드가 멈추거나 YAML 오류가 보이면 첫 오류 메시지와 설치 버전을 확인하세요. [설치 및 업로드 문제 해결](TROUBLESHOOTING.md)
