# HOST-W07 macOS 27 Arduino IDE Upload 교정

2026-11-24 KST macOS 27.2.1 (26B131) Apple Silicon ARM64와 Arduino IDE 2.3.11에서
새 제품 source `97c7cd01ff59fb5ae3689e9de62b9c820b83fd5e`의 비공개 `0.6.0-rc.1` 일반 Upload를 검증했다.
C11의 원형 `No module named 'yaml'` 실패는 [337번](<337_HOST_W07_C11_macOS_27_실기_검증과_마감.md>)에 보존한다.

Boards Manager는 의존성이 적은 초기 Python 3.12.16에서 builder를 실행한다. C11 Upload는 그 Python에서 PyYAML을
import하다가 probe 선택 전에 종료됐다. C12는 package의 runner YAML 검증과 pyOCD inventory를 고정 SDK Python으로 수행한다.
기존 manifest·runner 인자·명시 probe 검증 및 session/cache/probe lock과 flash 실행 정책은 그대로 적용된다.

| 항목 | 결과 |
| --- | --- |
| 고정 입력 | board `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, NCS 3.4.0 / `ccc010f809`, `/opt/nordic/ncs` |
| 새 package·kit | 독립 package와 sidecar 두 번의 byte 일치. package SHA-256 `df37b6fde6471398de8f597dbf0e01f7de0db0b0f30cf686f8e7b3d8c34d85a8`, kit SHA-256 `db339b02d308e74e13c5ee98b3185ca11d341c9ac6ebc3fc7e06cc5cc80d727e`. |
| 신규 설치 | 새 로컬 state에서 고정 SDK 검증, lifecycle, device inventory PASS. GUI Boards Manager 설치본 파일 960개 대조 PASS. |
| 일반 Upload | `nucode:zephyr:nu54dk:upload_probe=pyocd,feature_set=standard`. 실제 VCOM과 명시 UID가 가리키는 NU54DK에서 일반 sector 20개·81,920 bytes를 프로그램했다. `NU54_UPLOAD_PASS`, `Done uploading.`, runner exit 0을 확인했다. |
| firmware와 runtime | C11 같은 Mac과 같은 standard Blink의 BIN·HEX가 동일했다. C12의 IDE 산출물과 같은 보드에서 GPIO 전이 9회, register write 없이 probe close와 worker exit 0. |
| 회귀 | M8 upload 21개, M9 flash lock/도구 identity 2개, host upload process 7개 PASS. M9 Windows file sharing fixture의 Mac 실패는 수정 전 source에서도 동일하게 재현됐다. |
| 정리 | IDE 정상 종료, 보유 프로세스·포트 없음, w06 PAUSED. C11과 C12의 source별 기록은 독립으로 보존한다. |

C12 exact CI는 [M12 45207890683](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/45207890683)에서 추적한다.
사용자 지시에 따라 macOS26과 Ubuntu24.04는 다시 시험하지 않았다. 이 검증은 C12의 해당 업로드 경로를 확인했으며 [최종 배포 후보 심사](<../05_릴리스/v0.6.0/RELEASE_CHECKLIST.md>)는 계속한다.

## 로컬 증거 SHA-256

로컬 `work/mac27-ide-upload-fix.a45AYG/control`과 새 attempt에 원형과 exit code를 보존했다.

| 항목 | SHA-256 |
| --- | --- |
| `producer` | `0e65b40e2ebec3a5c4d5d03ed6cc838b269e3292a3789ee966ed19a772a5fd84` |
| `kit_manifest` | `5c3bdb43cd846b5484bbfd63c8de0542c7fa8597a7aebdeabe768e6be4a37a5b` |
| `IDE_console` | `f0d99d650c74e97bb05a12f6b39cf4de124db4da9f774aa2f505fbd1a779ac1b` |
| `IDE_install_audit` | `b30c4875e10dd8d4cf1f24635efe1a1bd583aafddf537f3374c6537cc0c65a03` |
| `IDE_flash_log` | `004cf42af36e263b393036f2a349e6ba585cde557aaa8989c97152bed4b17bff` |
| `Blink_runtime` | `d6a7fcfc366c034ed99bd924624a8e40f25a4c6945573c672229555126eab717` |
| `BIN_HEX_comparison` | `4bb328924bfeb0427a6dfca1a869699611356563b2b3dc6beec7bb230fa29768` |
| `STOP_cleanup` | `3188805cf119825b4283efee8db7e7f24a220b65f9dccc2cbb200cb4625fc639` |
