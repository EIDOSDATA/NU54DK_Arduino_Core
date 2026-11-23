"""! @brief SDK pyOCD가 probe를 열기 전에 같은 설치본의 firmware 금지 보호를 실행합니다. """
import importlib.util
import json
from pathlib import Path
import sys

guard_path=Path(__file__).resolve().parent/'nu54_builder_impl/probe_guard.py'
spec=importlib.util.spec_from_file_location('nu54_installed_pyocd_guard',guard_path)
module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module
spec.loader.exec_module(module)
proof=module.guard_session(session)
print('NU54_PROBE_GUARD='+json.dumps({key:value for key,value in proof.items() if key!='events'},sort_keys=True),flush=True)
