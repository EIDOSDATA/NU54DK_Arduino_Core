# NU54DK Arduino Core

NU54DK에서 Loader 없이 동작하는 Native Full Zephyr 기반 Arduino Core입니다.

## 현재 상태

- 아키텍처 결정 완료
- 저장소 기본 구조 생성 완료
- NU54DK Zephyr 보드 패키지 서브모듈 연결 완료
- west-native Blink PoC 구현 예정

## 보드 정의

NU54DK의 물리 핀, 주변장치, pinctrl 및 runner 정보는 별도 저장소를 단일 원본으로 사용합니다. Arduino Core 저장소에는 해당 저장소를 다음 경로의 Git 서브모듈로 고정합니다.

- [Nucode01/NU54DK_Zephyr_DTS](https://github.com/Nucode01/NU54DK_Zephyr_DTS)
- `board_package/NU54DK_Zephyr_DTS`

Arduino Core 안에 독립적인 보드 DTS 복사본을 만들지는 않습니다. 빌드할 때 서브모듈 루트를 Zephyr의 `BOARD_ROOT`로 전달합니다.

~~~text
-DBOARD_ROOT=<NU54DK_Arduino_Core>/board_package/NU54DK_Zephyr_DTS
~~~

소스 저장소를 처음 복제할 때는 서브모듈도 함께 내려받아야 합니다.

~~~shell
git clone --recurse-submodules <NU54DK_Arduino_Core 저장소 URL>
~~~

이미 저장소를 복제했다면 다음 명령을 사용합니다.

~~~shell
git submodule update --init --recursive
~~~

Boards Manager용 배포 archive에는 고정된 서브모듈 commit의 실제 보드 파일을 같은 경로에 포함합니다. 따라서 Arduino IDE 사용자는 Git이나 서브모듈 명령을 따로 실행하지 않습니다.

## 문서

- [개발 방식 비교 및 아키텍처 결정](./00_Docs/00_사전%20리서치/01_개발_방식_비교_및_아키텍처_결정.md)
- [저장소 폴더 구조](./00_Docs/01_아두이노%20코어%20설계/01_저장소_폴더_구조.md)
