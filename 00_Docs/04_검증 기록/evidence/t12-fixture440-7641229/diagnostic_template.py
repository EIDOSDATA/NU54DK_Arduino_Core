"""! @brief 새 확인과 exact pair를 준비한 다음 runner에 설치할 읽기 전용 진단 hook입니다.

@details 이 파일은 준비 파일이며 호출한 실행에서만 동작합니다.
          canonical confirmation·flash·lease·판정·cleanup은 호출한 runner가 그대로 수행합니다.
"""
import json


def install(pair, output_path):
    """! @brief 정식 prepare/start 응답 뒤 GPIO와 신호 경로 설정만 추가로 읽습니다. """
    original = pair.Device.command
    trace = output_path.open('x', encoding='utf-8', newline='\n')
    registers = {
        'PDM20_ENABLE': 0x500D0500, 'PDM20_MODE': 0x500D0508,
        'PDM20_PSEL_CLK': 0x500D0540, 'PDM20_PSEL_DIN': 0x500D0544,
        'PDM21_ENABLE': 0x500D1500, 'PDM21_MODE': 0x500D1508,
        'PDM21_PSEL_CLK': 0x500D1540, 'PDM21_PSEL_DIN': 0x500D1544,
        'SPIS21_ENABLE': 0x500C7500,
        'GPIOTE20_CONFIG0': 0x500DA510, 'GPIOTE20_CONFIG1': 0x500DA514,
        'GPIOTE20_PUBLISH_IN0': 0x500DA180, 'GPIOTE20_SUBSCRIBE_OUT1': 0x500DA084,
        'DPPI20_CHEN': 0x500C2500, 'GPIO1_IN': 0x500D820C,
    }

    def command(device, opcode, values=(), timeout=10):
        """! @brief 원래 명령 결과와 예외는 유지하며 진단 raw 값을 별도로 보존합니다. """
        result = original(device, opcode, values, timeout)
        if opcode in (34, 35):
            trace.write(json.dumps({'role': device.image['role'], 'opcode': opcode,
                'arguments': list(values), 'source': device.image['core_revision'],
                'registers': {name: device.target.read32(address) for name, address in registers.items()},
                'signal_pin_cnf': {str(pin): device.target.read32(0x500D8280 + 4 * pin) for pin in (4, 5, 6, 7)},
                'scope': 'passive register reads after canonical command; not waveform measurement'}) + '\n')
            trace.flush()
        return result

    pair.Device.command = command
    return trace
