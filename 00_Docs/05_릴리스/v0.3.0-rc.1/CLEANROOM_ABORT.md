# v0.3.0-rc.1 public clean-room 검증 중단 기록

| 항목 | 내용 |
| --- | --- |
| 기록 ID | RELEASE-v0.3.0-rc.1-CLEANROOM-ERRATUM-001 |
| 대상 | `v0.3.0-rc.1` |
| 판정 | **Public Prerelease 보존 / formal M22 clean-room 검증 중단** |
| 판정일 | 2026-09-02 |
| 교정 후보 | `v0.3.0-rc.2` — 아직 공개 전 |
| 현재 stable | `v0.2.0` — 변경 없음 |
| 작성자 | Quantum / NUCODE |

## 1. 요약

`v0.3.0-rc.1`은 exact source에서 package 재현성과 세 개의 local fixed gate를 통과한 뒤
Public GitHub Prerelease로 공개됐습니다. 이어서 실행한 public URL 기반 동일 PC 격리
clean-room은 Nordic Toolchain 설치 단계에서 중단됐고 M22 final evidence는 생성되지
않았습니다.

원인은 release clean-room harness가 격리 root 아래의 모든 layout path를 먼저 만들면서
Nordic installer가 직접 생성해야 할 Toolchain 대상 leaf까지 빈 directory로 만든 것입니다.
`nrfutil sdk-manager`는 이미 존재하는 설치 directory를 거부했습니다.

이 결과를 일반 Arduino 사용자 package의 firmware, API 또는 정상 clean install 결함으로
확대하지 않습니다. 다만 M22가 요구하는 공개 URL 전체 수명주기를 끝까지 통과하지 못했으므로
RC1을 `public-rc1-validated`로 선언하지 않습니다.

## 2. 불변 Release identity

| 항목 | 값 |
| --- | --- |
| Core commit | `8dafcb722dc31ef5890922b92a5b7ee8dd91c32f` |
| Board package | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Annotated tag | `v0.3.0-rc.1` |
| Tag object | `4657f2a267e3ef045571ff2a8b5f6fed60d61e69` |
| Release 공개 시각 | `2026-09-01T14:44:23Z` |
| Release URL | <https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.3.0-rc.1> |
| Plan SHA-256 | `a99c0998c61ad0fe2ffb43b7093626e5ad57760650a422b4bf3949ec219b1217` |

RC1 tag와 자산은 실패를 숨기기 위해 이동, 삭제, 교체 또는 재업로드하지 않습니다.

## 3. 공개 자산

| 파일 | 크기 | SHA-256 |
| --- | ---: | --- |
| `nucode-nu54dk-zephyr-0.3.0-rc.1.zip` | 1,657,530 | `e40245fd7236dadd5cb79fc394d1fa92944f53b207ad9314274d8257e538afd8` |
| `nucode-nu54dk-zephyr-0.3.0-rc.1.CHECKSUMS.sha256` | 572 | `a34ed1f67910bebb1dd9473dd3c3d34d23380d1ff98b48dd720036e1d46b1189` |
| `nucode-nu54dk-zephyr-0.3.0-rc.1.license-inventory.json` | 15,632 | `77477fb846fad60a67bd013b28b72ba114761a09e0534366fd3171e7e36faa09` |
| `nucode-nu54dk-zephyr-0.3.0-rc.1.release-manifest.json` | 93,281 | `c8e1eb6ec83d034956eb742bbc84d98704dce29ba56abb1caf56cbb54143ff0c` |
| `nucode-nu54dk-zephyr-0.3.0-rc.1.THIRD_PARTY_NOTICES.md` | 1,813 | `d748669517ba571923cd86fc7adee164945cdf3c36ba391510121c170507282d` |
| `nucode-nu54dk-zephyr-0.3.0-rc.1.spdx.json` | 174,413 | `62c0d3c2b2fa87a83f993675c9963d7237f4f5d7a63569245e87b2c3b217e08b` |
| `package_nucode_nu54dk_rc_index.json` | 1,151 | `124d00ebd440dd893ba4b476650fb5938e61693b17bfd6aa8f7df77675815cfd` |

공개 Release에는 위 7개만 존재했습니다. Plan, private evidence, log와 stable index는 Release
자산이 아닙니다.

## 4. Gate 결과

| Gate | 상태 | Evidence 크기 | Evidence SHA-256 |
| --- | --- | ---: | --- |
| `host` | PASS | 937 | `3a720a419e9cd3869268b1d38a39a391d19ac44b15795b265737d9093b16215f` |
| `package-examples` | PASS | 1,043 | `b8cdb7ae488bbc8923a17f3dda3ea0625e2b6a8e29532b4ecb824d108503443b` |
| `rc-upload` | PASS | 1,029 | `c32685db9f7713bc9e0b563dbd1e17b0a0caefe3ab9261fd23180f4370d97773` |
| `cleanroom` | **FAIL** | 1,980 | `52f9f09acdf11f3b8615adc91a6dd73e21b76bc6515488cb25e2c7a05e68d979` |

Redacted public clean-room log는 5,367 byte이며 SHA-256은
`8612fbe32473d925947e88009fb1c1cec9ed8af2edc55705c10a005f2d170a74`입니다.

세 fixed gate의 PASS는 실제 수행된 RC1 증거로 유지합니다. 그러나 네 gate가 모두 PASS해야 하는
M22 final 판정을 대신하지 않으며 RC2 증거로 상속하지 않습니다.

## 5. 실패 지점과 원인

Clean-room evidence에는 다음 단계까지 기록됐습니다.

1. Arduino CLI exact identity 확인
2. Public RC index exact byte 확인
3. Boards Manager index 갱신과 cached index exact byte 확인
4. RC1 package 다운로드와 platform 설치 명령 완료
5. 설치 version 목록 확인

Post-install의 Nordic Toolchain 단계에서 다음 의미의 오류가 발생했습니다.

```text
Install directory ...\profile\ncs\toolchains\dcbdc366a1 already exists
```

Tagged clean-room runner는 실행 준비 과정에서 `ncs`와 `toolchain`을 포함한 모든 layout path에
`mkdir`을 적용했습니다. 격리라는 목적에는 맞지만 Nordic installer가 비어 있는 exact install
leaf도 거부하므로 실행 계약과 충돌했습니다. 교정 runner는 필요한 상위·작업 directory만 만들고
NCS와 Toolchain 설치 leaf는 installer가 직접 생성하게 해야 합니다.

## 6. Cleanup과 증거 보존

실패 evidence의 cleanup 상태는 `preserved-for-failure`입니다. 실패 당시 exact run leaf
`C:\NU54CI\M22\m22-20260901T144550Z-b576f5f5`는 원인 조사용으로 자동 삭제하지 않았습니다.
외부 evidence와 redacted log도 별도로 보존했습니다.

실패 leaf를 정리하더라도 원본 evidence, log, identity와 정리 승인을 먼저 보존해야 합니다.
상위 `C:\NU54CI\M22`, sibling run 또는 외부 evidence directory를 재귀 삭제 대상으로 사용하면
안 됩니다.

## 7. Stable 불변 확인

| 항목 | 고정 값 |
| --- | --- |
| Stable index | `package_nucode_nu54dk_index.json` |
| 크기 | 1,877 byte |
| SHA-256 | `5ae7fbe13f71c52950879064685694cf4b062557572f187e81476639724e5344` |
| Git blob | `b2a3ac2d4c3babf366541406764e5f900f2f4e6d` |
| Version 순서 | `0.2.0`, `0.1.0` |

RC1 공개와 clean-room 실패 처리 과정에서 stable index를 RC 자산으로 올리거나 RC version을
추가하지 않았습니다.

## 8. 후속 결정

1. RC1 tag와 7개 자산은 불변 역사 기록으로 유지합니다.
2. RC1 Release 설명은 formal validation이 중단됐고 RC2가 후속 후보라는 상태만 표시할 수
   있습니다.
3. Clean-room install-leaf 교정과 회귀시험은 새 Core commit에 기록합니다.
4. `v0.3.0-rc.2`는 새 plan, package, tag, 자산과 네 gate evidence를 가져야 합니다.
5. RC2 public clean-room과 final evidence 전에는 `v0.3.0` stable 승격을 진행하지 않습니다.

## 9. 관련 문서

- [M22 RC1 상세 검증 기록](<../../04_검증 기록/29_M22_v0.3.0_rc1_통합_릴리스_기준선.md>)
- [RC2 릴리스 후보 문서](../v0.3.0-rc.2/README.md)
- [M22 RC2 검증 기록](<../../04_검증 기록/30_M22_v0.3.0_rc2_통합_릴리스_기준선.md>)
