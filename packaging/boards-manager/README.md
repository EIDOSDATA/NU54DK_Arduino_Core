# NU54DK Boards Manager 패키징

이 디렉터리의 도구는 작업 트리가 아니라 지정한 Git commit만 입력으로 사용한다. 상위
저장소의 `board_package/NU54DK_Zephyr_DTS` gitlink가 가리키는 commit도 함께 펼쳐서
하나의 Arduino platform ZIP으로 만든다.

지원하는 M10 preview 버전은 `0.0.90`, `0.0.91`이다.

```powershell
python .\packaging\boards-manager\nu54_package.py build `
  --repo-root . `
  --output-dir .\build\boards-manager `
  --version 0.0.90 `
  --commit HEAD `
  --update-index
```

두 버전을 모두 만든 뒤 최신 버전 순서의 공식 index를 다시 만들 수 있다.

```powershell
python .\packaging\boards-manager\nu54_package.py index `
  --output-dir .\build\boards-manager `
  --versions 0.0.90 0.0.91
```

검증은 ZIP 경로 안전성, 단일 top-level 디렉터리, timestamp·mode·정렬, manifest 계약,
전체 checksum, SPDX JSON SBOM, 라이선스 원문 inventory, package index URL·크기·checksum을
모두 확인하며 하나라도 다르면 실패한다.

```powershell
python .\packaging\boards-manager\nu54_package.py validate `
  --archive .\build\boards-manager\nucode-nu54dk-zephyr-0.0.90.zip `
  --expected-version 0.0.90

python .\packaging\boards-manager\nu54_package.py validate-index `
  --index .\build\boards-manager\package_nucode_nu54dk_preview_index.json `
  --artifact-dir .\build\boards-manager
```

생성되는 ZIP은 `m10-preview-<version>` GitHub prerelease asset URL을 사용한다. NCS와 Nordic
toolchain은 이 ZIP이나 index의 `tools` 항목으로 재배포하지 않는다. 라이선스 inventory의
법률 검토 상태는 최종 공개 Release 전까지 의도적으로 `required`로 유지한다.

보드 서브모듈은 저장소 최상위 `LICENSE`의 MIT 범위와
`boards/nucode/nu54dk/**` 파생 파일의 Apache-2.0 범위를 분리해 기록한다. nRF Util,
sdk-manager, NCS, Zephyr, Nordic toolchain, bundled pyOCD 및 선택형 J-Link는 ZIP에 포함하지
않는 외부 전제조건이며, 확인하지 않은 종합 라이선스를 추정하지 않고 `NOASSERTION`으로
유지한다.
