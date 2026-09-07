"""! @brief cache 정리 전에 개별 설치 build의 live/configure 원본을 즉시 보존합니다. """
from pathlib import Path
import ast
import hashlib
import importlib.util
import json
import shutil
import sys
import yaml

work = Path(__file__).parent
root = Path('C:/u4y')
proof = json.loads((work / 'verified-package-reproducibility.json').read_text(encoding='utf-8'))
tree = ast.parse((work / 'installed_examples.py').read_text(encoding='utf-8'))
definitions = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in ('sha', 'save', 'verify_identity')], type_ignores=[])
exec(compile(ast.fix_missing_locations(definitions), str(work / 'installed_examples.py'), 'exec'), globals())
for name in sys.argv[1:]:
    manifests = list((root / name).glob('*.nu54-build.json'))
    assert len(manifests) == 1
    verify_identity(manifests[0])
    print('RETRY_IDENTITY_PRESERVED=' + name)
