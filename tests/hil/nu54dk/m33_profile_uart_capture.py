"""! @file
@brief 원형 readline 소비 형태를 유지하며 PROBE 전부터 닫기까지 UART 원문을 수집합니다.
@note 원형 pre-PROBE input clear 이전 byte는 수집 범위가 아닙니다. 장치 import는 없습니다.
"""
import hashlib
from pathlib import Path
import threading
import time


class CapturePort:
    """! @brief 단일 reader가 원문을 먼저 저장하고 원형 소비자에게 byte 순서를 전달합니다. """
    def __init__(self, real, role, prefix, maximum=8 * 1024 * 1024):
        self.real = real
        self.role = role
        self.timeout = real.timeout
        self.write_timeout = real.write_timeout
        self.maximum = maximum
        self.condition = threading.Condition()
        self.pending = bytearray()
        self.events = []
        self.errors = []
        self.reported_errors = 0
        self.stop_reader = threading.Event()
        self.thread = None
        self.started = False
        self.closed = False
        self.read_bytes = 0
        self.delivered_bytes = 0
        self.written_bytes = 0
        self.high_water = 0
        self.last_rx = None
        self.rx_path = Path(prefix).with_suffix(f'.{role}.rx.bin')
        self.tx_path = Path(prefix).with_suffix(f'.{role}.tx.bin')
        self.rx = self.rx_path.open('xb')
        try:
            self.tx = self.tx_path.open('xb')
        except BaseException:
            self.rx.close()
            raise

    @property
    def is_open(self):
        """! @brief 실제 포트 상태를 원형 close 검사에 전달합니다. """
        return self.real.is_open

    def _error(self, stage, error):
        """! @brief 오류 문자열이나 원시 장치 ID 없이 오류 종류와 위치를 보존합니다. """
        with self.condition:
            if len(self.errors) < 16:
                self.errors.append({'stage': stage, 'type': type(error).__name__})
            self.condition.notify_all()

    def _read(self):
        """! @brief 단일 reader만 실제 RX를 읽고 flush 후 큐에 같은 byte를 전달합니다. """
        while not self.stop_reader.is_set():
            try:
                ## @brief 빈 큐에서는 한 byte만 기다려 고정 256-byte 묶음의 추가 지연을 피합니다.
                waiting = self.real.in_waiting
                if type(waiting) is not int or waiting < 0:
                    raise ValueError('Invalid UART pending byte count')
                data = self.real.read(max(1, min(waiting, 256)))
                if not isinstance(data, bytes):
                    raise TypeError('Serial read must return bytes')
                if not data:
                    continue
                self.read_bytes += len(data)
                self.last_rx = data[-1]
                if self.read_bytes > self.maximum:
                    raise BufferError('Raw capture limit')
                if self.rx.write(data) != len(data):
                    raise OSError('Short RX capture file write')
                self.rx.flush()
                with self.condition:
                    if len(self.pending) + len(data) > self.maximum:
                        raise BufferError('Consumer queue limit')
                    self.pending.extend(data)
                    self.high_water = max(self.high_water, len(self.pending))
                    self.condition.notify_all()
            except BaseException as error:
                self._error('reader', error)
                return

    def reset_input_buffer(self):
        """! @brief 원형 최초 clear 한 번 뒤에만 reader를 시작하고 이후 clear는 거부합니다. """
        if self.started or self.closed:
            raise RuntimeError('Duplicate or late input clear')
        self.real.reset_input_buffer()
        self.events.append({'kind': 'original_preprobe_clear', 'monotonic_ns': time.monotonic_ns()})
        self.started = True
        self.thread = threading.Thread(target=self._read, name='w06-rx-' + self.role, daemon=True)
        self.thread.start()

    def readline(self):
        """! @brief 원형 timeout과 개행/부분행 형태를 유지하며 새로운 수집 오류는 한 번 전달합니다. """
        if not self.started or self.closed:
            raise RuntimeError('Capture port not active')
        deadline = time.monotonic() + self.timeout
        with self.condition:
            while True:
                if self.reported_errors < len(self.errors):
                    self.reported_errors = len(self.errors)
                    raise OSError('Raw capture incomplete')
                newline = self.pending.find(b'\n')
                if newline >= 0:
                    size = newline + 1
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    size = len(self.pending)
                    break
                self.condition.wait(remaining)
            data = bytes(self.pending[:size])
            del self.pending[:size]
            self.delivered_bytes += len(data)
            return data

    def write(self, payload):
        """! @brief 송신 원문과 반환량을 남기며 동일 API 한 번만 호출합니다. """
        if not self.started or self.closed or not isinstance(payload, bytes):
            raise RuntimeError('Capture write outside active boundary')
        try:
            if self.tx.tell() + len(payload) > self.maximum or len(self.events) >= 4096:
                raise BufferError('TX capture limit')
            if self.tx.write(payload) != len(payload):
                raise OSError('Short capture file write')
            self.tx.flush()
            sent = self.real.write(payload)
            if type(sent) is not int or not 0 <= sent <= len(payload):
                raise TypeError('Invalid serial write result')
            self.written_bytes += sent
            self.events.append({'kind': 'write', 'requested': len(payload), 'returned': sent,
                                'monotonic_ns': time.monotonic_ns()})
            if sent != len(payload):
                raise OSError('Short UART write')
            return sent
        except BaseException as error:
            self._error('write', error)
            raise

    def flush(self):
        """! @brief 원형 flush를 한 번 위임하고 기존 write timeout을 넘긴 반환도 실패로 남깁니다. """
        if not self.started or self.closed:
            raise RuntimeError('Capture flush outside active boundary')
        began = time.monotonic()
        try:
            result = self.real.flush()
            if time.monotonic() - began > self.write_timeout:
                raise TimeoutError('UART flush deadline')
            return result
        except BaseException as error:
            self._error('serial_flush', error)
            raise

    def close(self):
        """! @brief 유한 join과 실제 close를 모두 시도하고 남은 byte/reader를 성공으로 숨기지 않습니다. """
        if self.closed:
            return
        self.stop_reader.set()
        if self.thread is not None:
            self.thread.join(0.25)
        try:
            if self.real.is_open and self.real.in_waiting:
                self._error('unread_device_queue_at_close', BufferError())
        except BaseException as error:
            self._error('device_queue_at_close', error)
        try:
            self.real.close()
        except BaseException as error:
            self._error('serial_close', error)
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(0.25)
        if self.thread is not None and self.thread.is_alive():
            self._error('reader_join', RuntimeError())
        for stream in (self.rx, self.tx):
            try:
                stream.close()
            except BaseException as error:
                self._error('capture_file_close', error)
        self.closed = True
        if self.real.is_open is not False:
            raise OSError('Serial remained open')

    def receipt(self):
        """! @brief 원문 해시·큐 잔여·개행·reader/close를 모두 종료 판정에 결합합니다. """
        with self.condition:
            pending = len(self.pending)
        joined = self.thread is not None and not self.thread.is_alive()
        complete = (self.started and self.closed and joined and self.real.is_open is False
                    and not self.errors and pending == 0 and self.last_rx == 10
                    and self.read_bytes == self.delivered_bytes
                    and self.rx_path.stat().st_size == self.read_bytes)
        return {'role': self.role, 'status': 'COMPLETE' if complete else 'INCOMPLETE',
                'boundary': 'AFTER_ORIGINAL_PREPROBE_CLEAR_THROUGH_CLOSE',
                'rx': {'path': self.rx_path.name, 'sha256': hashlib.sha256(self.rx_path.read_bytes()).hexdigest(),
                       'bytes': self.read_bytes},
                'tx': {'path': self.tx_path.name, 'sha256': hashlib.sha256(self.tx_path.read_bytes()).hexdigest(),
                       'bytes': self.tx_path.stat().st_size,
                       'returned_bytes': self.written_bytes},
                'delivered_bytes': self.delivered_bytes, 'unconsumed_bytes': pending,
                'queue_high_water': self.high_water, 'last_byte_newline': self.last_rx == 10,
                'reader_joined': joined, 'closed': self.closed and self.real.is_open is False,
                'errors': list(self.errors), 'events': list(self.events)}


class CaptureSerial:
    """! @brief 검토된 역할별 COM만 열고 실제 serial module 대신 원형 함수에 제공됩니다. """
    def __init__(self, module, mappings, prefix):
        self.module = module
        self.mappings = {row['port']: row['role'] for row in mappings}
        self.prefix = Path(prefix)
        if (len(mappings) != 3 or len(self.mappings) != 3
                or set(self.mappings.values()) != {'server', 'client', 'watcher'}):
            raise ValueError('Exact three-role UART mapping required')
        self.ports = {}

    def Serial(self, port, baudrate, timeout, write_timeout):
        """! @brief 원형 인자를 검사하고 역할당 포트를 한 번만 엽니다. """
        if (port not in self.mappings or self.mappings[port] in self.ports
                or baudrate != 115200 or timeout != 0.05 or write_timeout != 5.0):
            raise ValueError('Unexpected serial open')
        real = self.module.Serial(port, baudrate, timeout=timeout, write_timeout=write_timeout)
        role = self.mappings[port]
        try:
            captured = CapturePort(real, role, self.prefix)
        except BaseException:
            real.close()
            raise
        self.ports[role] = captured
        return captured

    def finish(self):
        """! @brief 누락 포트를 포함해 전체 세 역할의 최신 종료 증거만 반환합니다. """
        result = {}
        for role in ('server', 'client', 'watcher'):
            port = self.ports.get(role)
            if port is None:
                result[role] = {'role': role, 'status': 'INCOMPLETE', 'reason': 'NOT_OPENED'}
                continue
            try:
                port.close()
                result[role] = port.receipt()
            except BaseException as error:
                result[role] = {'role': role, 'status': 'INCOMPLETE', 'error_type': type(error).__name__}
        return result
