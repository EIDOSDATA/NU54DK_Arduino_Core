# NU54DK clean Windows SSH 구성

`setup-nu54-ci-ssh.ps1`은 M10 Boards Manager clean-machine 시험용 Windows PC를
SSH 검증기로 구성한다. 대상 PC에서 관리자 PowerShell로 한 번 실행한다.

## 1. 개발 PC에서 공개키 생성

~~~powershell
$KeyPath = Join-Path $env:USERPROFILE '.ssh\nu54dk_m10_ed25519'
ssh-keygen -t ed25519 -f $KeyPath -C 'NU54DK M10 clean Windows'
~~~

private key인 `nu54dk_m10_ed25519`는 개발 PC 밖으로 복사하지 않는다. 공개키인
`nu54dk_m10_ed25519.pub`만 USB 메모리 등을 이용해 대상 PC로 옮긴다.

## 2. 대상 PC에서 자동 구성

가장 간단한 방법은 다음 세 파일을 대상 PC의 같은 폴더에 복사한 뒤
`setup-nu54-ci-ssh.cmd`를 더블클릭하는 것이다.

~~~text
setup-nu54-ci-ssh.cmd
setup-nu54-ci-ssh.ps1
nu54dk_m10_ed25519.pub
~~~

배치 파일은 UAC 관리자 권한을 요청하고, 공개키와 PowerShell 구문을 확인한 뒤 전체 설정을
자동 실행한다. `nu54ci`가 없으면 저장하거나 출력하지 않는 임의 암호로 표준 계정을 만들고,
SSH는 처음부터 공개키 인증만 허용한다. 완료 화면의 IPv4 주소와 OpenSSH host key
fingerprint를 기록한다.

PowerShell에서 직접 실행하려면 관리자 PowerShell을 열고 다음 명령을 사용한다.

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\setup-nu54-ci-ssh.ps1 `
  -PublicKeyPath E:\nu54dk_m10_ed25519.pub
~~~

스크립트는 다음 작업을 수행한다.

- `nu54ci` 표준 로컬 사용자 생성 또는 기존 계정 확인
- OpenSSH Server 설치와 자동 시작 설정
- 공개키를 사용자 `authorized_keys`에 추가
- 공개키와 `.ssh` ACL 제한
- `PubkeyAuthentication`, `AllowUsers`와 암호 로그인 정책 설정
- SSH 방화벽을 기본적으로 `LocalSubnet`에 한정
- `sshd_config` 백업, 구문 검증과 안전한 서비스 재시작
- `C:\ncs`와 외부 build tool 존재 여부 진단
- 원격 작업 디렉터리 `NU54CI` 생성

특정 개발 PC IP만 허용하려면 다음처럼 실행한다.

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\setup-nu54-ci-ssh.ps1 `
  -PublicKeyPath E:\nu54dk_m10_ed25519.pub `
  -AllowedRemoteAddress 192.168.0.100
~~~

초기 진단 동안 SSH 암호 로그인을 유지해야 한다면
`-KeepPasswordAuthentication`을 추가한다. 공개키 접속이 확인된 뒤 해당 option 없이
다시 실행해 암호 로그인을 끈다.

## 3. 개발 PC에서 접속 확인

~~~powershell
Test-NetConnection -ComputerName <대상_PC_IP> -Port 22
ssh -i "$env:USERPROFILE\.ssh\nu54dk_m10_ed25519" nu54ci@<대상_PC_IP>
~~~

최초 접속 시 표시되는 fingerprint는 스크립트가 마지막에 출력한 OpenSSH host key와
비교한다.

## 보안 경계

- private key나 Windows 계정 암호를 저장소, 채팅 또는 대상 PC에 복사하지 않는다.
- 공유기에서 TCP 22 포트를 인터넷으로 포워딩하지 않는다.
- 같은 LAN 또는 신뢰할 수 있는 VPN 안에서만 사용한다.
- `sshd_config`는 변경 전에 timestamp가 포함된 `.bak` 파일로 보존된다.
- 대상 계정이 Administrators 그룹 구성원이면 스크립트가 중단된다.
