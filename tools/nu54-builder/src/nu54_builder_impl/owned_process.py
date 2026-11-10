"""! @brief 실행한 자식 묶음만 유한 시간 동안 소유하고 종료하는 공통 실행기입니다. """
from dataclasses import dataclass
import math
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
from typing import Mapping, Sequence


def finite_timeout(value):
    """! @brief 장치를 열기 전에 1800초 이하의 유한 실행 제한을 확인합니다. """
    if isinstance(value, bool):
        raise ValueError('timeout은 0초 초과 1800초 이하의 유한 수여야 합니다.')
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError('timeout은 0초 초과 1800초 이하의 유한 수여야 합니다.') from error
    if not math.isfinite(number) or not 0 < number <= 1800:
        raise ValueError('timeout은 0초 초과 1800초 이하의 유한 수여야 합니다.')
    return number


@dataclass(frozen=True)
class OwnedResult:
    """! @brief 실제 leader 종료 코드·출력과 자식 정리 결과를 분리합니다. """
    returncode: int
    stdout: bytes
    pid: int
    cleanup: dict


class OwnedTimeout(subprocess.TimeoutExpired):
    """! @brief 원형 부분 출력과 자식 정리 증거를 보존하는 timeout입니다. """
    def __init__(self, command, timeout, output, pid, cleanup):
        """! @brief 판정기는 이 예외의 원시 argv 대신 비식별 marker를 기록해야 합니다. """
        super().__init__(command, timeout, output=output)
        self.pid = pid
        self.cleanup = cleanup

    def __str__(self):
        """! @brief 기본 예외 표시에도 원시 probe UID·argv를 노출하지 않습니다. """
        return f'소유 명령의 제한 시간 {self.timeout}초를 초과했습니다.'


class OwnedInterrupted(KeyboardInterrupt):
    """! @brief 사용자 중단 뒤에도 부분 출력과 자식 정리 증거를 보존합니다. """
    def __init__(self, output, pid, cleanup):
        """! @brief 민감한 argv 없이 실제 정리 결과만 보유합니다. """
        super().__init__('명령이 중단되어 소유한 process를 정리했습니다.')
        self.output = output
        self.pid = pid
        self.cleanup = cleanup


class OwnedExecutionError(RuntimeError):
    """! @brief 예상하지 못한 OS·정리 실패의 부분 출력을 성공 주장 없이 보존합니다. """
    def __init__(self,output,error_type):
        """! @brief 원시 argv와 UID 대신 오류 type과 미확인 정리 상태만 표시합니다. """
        super().__init__('소유 명령의 시작 또는 정리를 확인하지 못했습니다: '+error_type)
        self.output = output
        self.error_type = error_type
        self.pid = None
        self.cleanup = {'status':'UNCONFIRMED','error_type':error_type}


def _posix(command, cwd, environment, capture, timeout):
    """! @brief 새 session의 process group만 정리하며 외부 process는 열거하지 않습니다. """
    process = subprocess.Popen(command, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
        stdout=capture, stderr=subprocess.STDOUT, start_new_session=True)
    expired = False
    interrupted = False
    returncode = None
    try:
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            expired = True
        except KeyboardInterrupt:
            interrupted = True
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
    return returncode, process.pid, expired, interrupted, {'strategy':'OWNED_POSIX_SESSION_GROUP',
        'leader_reaped':True,'final_group_kill_sent_or_group_absent':True}


def _windows(command, cwd, environment, capture, timeout):
    """! @brief Windows10+ Job List로 첫 명령 실행 전에 소유권을 원자적으로 묶습니다.
    @see https://devblogs.microsoft.com/oldnewthing/20230209-00/?p=107812
    """
    import ctypes as C
    from ctypes import wintypes as W
    import msvcrt

    class BasicLimit(C.Structure):
        """! @brief Win32의 원형 크기·정렬을 유지하는 기본 job 제한입니다. """
        _fields_ = [('ProcessTime',C.c_longlong),('JobTime',C.c_longlong),('Flags',W.DWORD),
            ('MinWorking',C.c_size_t),('MaxWorking',C.c_size_t),('ActiveLimit',W.DWORD),
            ('Affinity',C.c_size_t),('Priority',W.DWORD),('Scheduling',W.DWORD)]

    class IoCounters(C.Structure):
        """! @brief job 확장 구조의 원형 IO 통계 공간입니다. """
        _fields_ = [(name,C.c_ulonglong) for name in ('ReadOps','WriteOps','OtherOps','ReadBytes','WriteBytes','OtherBytes')]

    class ExtendedLimit(C.Structure):
        """! @brief 이름 없는 소유 job에만 kill-on-close를 설정합니다. """
        _fields_ = [('Basic',BasicLimit),('Io',IoCounters),('ProcessMemory',C.c_size_t),
            ('JobMemory',C.c_size_t),('PeakProcessMemory',C.c_size_t),('PeakJobMemory',C.c_size_t)]

    class Accounting(C.Structure):
        """! @brief 모든 소유 자식의 active 수가0인지 실제로 조회합니다. """
        _fields_ = [('UserTime',C.c_longlong),('KernelTime',C.c_longlong),
            ('PeriodUser',C.c_longlong),('PeriodKernel',C.c_longlong),('PageFaults',W.DWORD),
            ('Total',W.DWORD),('Active',W.DWORD),('Terminated',W.DWORD)]

    class Startup(C.Structure):
        """! @brief 명시한 stdin/stdout 두 handle만 child에 전달합니다. """
        _fields_ = [('cb',W.DWORD),('Reserved',W.LPWSTR),('Desktop',W.LPWSTR),('Title',W.LPWSTR),
            ('X',W.DWORD),('Y',W.DWORD),('XSize',W.DWORD),('YSize',W.DWORD),
            ('XChars',W.DWORD),('YChars',W.DWORD),('Fill',W.DWORD),('Flags',W.DWORD),
            ('Show',W.WORD),('ReservedBytes',W.WORD),('ReservedData',C.c_void_p),
            ('Input',W.HANDLE),('Output',W.HANDLE),('Error',W.HANDLE)]

    class StartupEx(C.Structure):
        """! @brief handle 목록과 job 목록을 process 생성에 함께 전달합니다. """
        _fields_ = [('Startup',Startup),('Attributes',C.c_void_p)]

    class ProcessInfo(C.Structure):
        """! @brief 이번 호출에서 생성한 process/thread handle만 소유합니다. """
        _fields_ = [('Process',W.HANDLE),('Thread',W.HANDLE),('Pid',W.DWORD),('Tid',W.DWORD)]

    kernel = C.WinDLL('kernel32',use_last_error=True)
    signatures = {
        'CreateJobObjectW':([C.c_void_p,W.LPCWSTR],W.HANDLE),
        'SetInformationJobObject':([W.HANDLE,C.c_int,C.c_void_p,W.DWORD],W.BOOL),
        'QueryInformationJobObject':([W.HANDLE,C.c_int,C.c_void_p,W.DWORD,C.c_void_p],W.BOOL),
        'TerminateJobObject':([W.HANDLE,W.UINT],W.BOOL),
        'CloseHandle':([W.HANDLE],W.BOOL),
        'GetCurrentProcess':([],W.HANDLE),
        'DuplicateHandle':([W.HANDLE,W.HANDLE,W.HANDLE,C.POINTER(W.HANDLE),W.DWORD,W.BOOL,W.DWORD],W.BOOL),
        'InitializeProcThreadAttributeList':([C.c_void_p,W.DWORD,W.DWORD,C.POINTER(C.c_size_t)],W.BOOL),
        'UpdateProcThreadAttribute':([C.c_void_p,W.DWORD,C.c_size_t,C.c_void_p,C.c_size_t,C.c_void_p,C.c_void_p],W.BOOL),
        'DeleteProcThreadAttributeList':([C.c_void_p],None),
        'CreateProcessW':([W.LPCWSTR,W.LPWSTR,C.c_void_p,C.c_void_p,W.BOOL,W.DWORD,C.c_void_p,
            W.LPCWSTR,C.c_void_p,C.POINTER(ProcessInfo)],W.BOOL),
        'WaitForSingleObject':([W.HANDLE,W.DWORD],W.DWORD),
        'GetExitCodeProcess':([W.HANDLE,C.POINTER(W.DWORD)],W.BOOL)}
    for name, (arguments, result) in signatures.items():
        function = getattr(kernel,name)
        function.argtypes = arguments
        function.restype = result

    def check(value):
        """! @brief Win32 실패를 무시하지 않고 정확한 오류 번호로 전달합니다. """
        if not value:
            raise C.WinError(C.get_last_error())
        return value

    job = check(kernel.CreateJobObjectW(None,None))
    handles = []
    initialized = False
    attributes = None
    info = ProcessInfo()
    expired = False
    interrupted = False
    returncode = None
    account = Accounting()
    try:
        limit = ExtendedLimit()
        limit.Basic.Flags = 0x2000
        check(kernel.SetInformationJobObject(job,9,C.byref(limit),C.sizeof(limit)))
        current = kernel.GetCurrentProcess()
        with open(os.devnull,'rb') as null:
            for original in (msvcrt.get_osfhandle(null.fileno()),msvcrt.get_osfhandle(capture.fileno())):
                duplicate = W.HANDLE()
                check(kernel.DuplicateHandle(current,original,current,C.byref(duplicate),0,True,2))
                handles.append(duplicate.value)
            size = C.c_size_t()
            kernel.InitializeProcThreadAttributeList(None,2,0,C.byref(size))
            if not size.value:
                raise C.WinError(C.get_last_error())
            attributes = C.create_string_buffer(size.value)
            check(kernel.InitializeProcThreadAttributeList(attributes,2,0,C.byref(size)))
            initialized = True
            inherited = (W.HANDLE*2)(*handles)
            jobs = (W.HANDLE*1)(job)
            check(kernel.UpdateProcThreadAttribute(attributes,0,0x20002,inherited,C.sizeof(inherited),None,None))
            check(kernel.UpdateProcThreadAttribute(attributes,0,0x2000D,jobs,C.sizeof(jobs),None,None))
            startup = StartupEx()
            startup.Startup.cb = C.sizeof(startup)
            startup.Startup.Flags = 0x100
            startup.Startup.Input = handles[0]
            startup.Startup.Output = startup.Startup.Error = handles[1]
            startup.Attributes = C.cast(attributes,C.c_void_p)
            env = C.create_unicode_buffer('\0'.join(key+'='+value for key,value in
                sorted(environment.items(),key=lambda item:item[0].casefold()))+'\0\0')
            line = C.create_unicode_buffer(subprocess.list2cmdline(command))
            check(kernel.CreateProcessW(command[0],line,None,None,True,
                0x80000|0x400|0x200|0x8000000,env,str(cwd),C.byref(startup),C.byref(info)))
        deadline = time.monotonic()+timeout
        try:
            while True:
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    expired = True
                    break
                state = kernel.WaitForSingleObject(info.Process,max(1,min(50,math.ceil(remaining*1000))))
                if state == 258:
                    continue
                if state != 0:
                    raise C.WinError(C.get_last_error())
                code = W.DWORD()
                check(kernel.GetExitCodeProcess(info.Process,C.byref(code)))
                returncode = int(code.value)
                break
        except KeyboardInterrupt:
            interrupted = True
    finally:
        try:
            check(kernel.QueryInformationJobObject(job,1,C.byref(account),C.sizeof(account),None))
            if account.Active:
                check(kernel.TerminateJobObject(job,124))
            if info.Process:
                if kernel.WaitForSingleObject(info.Process,5000) != 0:
                    raise RuntimeError('소유 Windows leader의 종료가 완료되지 않았습니다.')
            deadline = time.monotonic()+5
            while True:
                check(kernel.QueryInformationJobObject(job,1,C.byref(account),C.sizeof(account),None))
                if account.Active == 0:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('소유 Windows job의 자식 정리가 완료되지 않았습니다.')
                time.sleep(0.01)
        finally:
            for handle in (info.Thread,info.Process,*handles):
                if handle:
                    kernel.CloseHandle(handle)
            if initialized:
                kernel.DeleteProcThreadAttributeList(attributes)
            kernel.CloseHandle(job)
    return returncode,int(info.Pid),expired,interrupted,{'strategy':'ATOMIC_WINDOWS_JOB_LIST',
        'active_processes_after':int(account.Active),'kill_on_last_handle_close':True}


def run_owned(command: Sequence[str | Path], *, cwd: Path, environment: Mapping[str,str],
        capture_directory: Path, timeout: float) -> OwnedResult:
    """! @brief 절대 executable·절대 경로·유한 timeout으로만 실행하고 raw 출력은 호출자에게 돌려줍니다. """
    argv = [str(value) for value in command]
    timeout = finite_timeout(timeout)
    if (not argv or not Path(argv[0]).is_absolute() or not Path(argv[0]).is_file()
            or not cwd.is_absolute() or not cwd.is_dir() or not capture_directory.is_absolute()
            or isinstance(timeout,bool) or not math.isfinite(timeout) or not 0 < timeout <= 1800
            or any('\0' in value for value in argv)):
        raise ValueError('명시한 절대 executable·directory와 1800초 이하 유한 timeout이 필요합니다.')
    values = dict(environment)
    folded = set()
    for key,value in values.items():
        if not key or '=' in key[1:] or '\0' in key or '\0' in value:
            raise ValueError('잘못된 child 환경 변수입니다.')
        if os.name == 'nt' and key.casefold() in folded:
            raise ValueError('Windows child 환경에 같은 이름이 중복됐습니다.')
        folded.add(key.casefold())
    capture_directory.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryFile(mode='w+b',dir=capture_directory) as capture:
        function = _windows if os.name == 'nt' else _posix
        try:
            returncode,pid,expired,interrupted,cleanup = function(argv,cwd,values,capture,timeout)
        except BaseException as error:
            capture.seek(0)
            output = capture.read()
            if isinstance(error,KeyboardInterrupt):
                raise OwnedInterrupted(output,None,{'status':'UNCONFIRMED_INTERRUPTED_DURING_CLEANUP'}) from None
            raise OwnedExecutionError(output,type(error).__name__) from None
        capture.seek(0)
        output = capture.read()
    if interrupted:
        raise OwnedInterrupted(output,pid,cleanup)
    if expired:
        raise OwnedTimeout(argv,timeout,output,pid,cleanup)
    return OwnedResult(returncode,output,pid,cleanup)
