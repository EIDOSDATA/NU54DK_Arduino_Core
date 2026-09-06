"""! @brief 고정 SDK 환경과 UID 비공개 출력을 준비합니다. """
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import re
import sys

REPO = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
WORK = Path(__file__).resolve().parent
BUNDLE = Path(r'C:\ncs\toolchains\dcbdc366a1')
BUILD = Path(r'C:\u3u')
SOURCE = (WORK / 'source.txt').read_text(encoding='ascii').strip()
spec = importlib.util.spec_from_file_location('connected_builder', REPO / 'tools/nu54-builder/src/nu54_builder.py')
builder = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = builder
spec.loader.exec_module(builder)
os.environ['PATH'] = os.pathsep.join([str(Path(os.environ['SystemRoot']) / 'System32'), os.environ['SystemRoot'], r'C:\Program Files\Git\cmd'])
os.environ.update(builder.apply_toolchain_environment(BUNDLE))
os.environ['PYTHONUTF8'] = '1'
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
from pyocd.core.helpers import ConnectHelper
HASHES = ['32f71533ff6ba27fd38ed32a17bf6d80a90d4f4980221051ed5c5a2e7fdb63a9', '4574ee31f25fe05f154395ea4d8c6aa0583b04a4f7a0ea97fe3d13b05eea8ca0']
probes = {hashlib.sha256(p.unique_id.strip().lower().encode()).hexdigest(): p.unique_id.strip().lower() for p in ConnectHelper.get_all_connected_probes(blocking=False)}
assert set(probes) == set(HASHES), 'The observed exact two-probe set changed'
UIDS = [probes[digest] for digest in HASHES]

def redact(value):
    if isinstance(value, str):
        for uid, digest in zip(UIDS, HASHES):
            value = re.sub(re.escape(uid), '<probe-sha256:' + digest + '>', value, flags=re.I)
        return value
    if isinstance(value, dict):
        return {redact(key): redact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return value

class RedactedStream:
    def __init__(self, stream):
        self.stream = stream
    def write(self, value):
        return self.stream.write(redact(value))
    def flush(self):
        return self.stream.flush()
    def __getattr__(self, name):
        return getattr(self.stream, name)

sys.stdout = RedactedStream(sys.stdout)
sys.stderr = RedactedStream(sys.stderr)
original_dumps = json.dumps
json.dumps = lambda value, *args, **kwargs: original_dumps(redact(value), *args, **kwargs)
sys.path.insert(0, str(REPO / 'tests/hil/nu54dk'))

def write_new(path, payload):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
