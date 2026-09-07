from pathlib import Path
import importlib.util,os,subprocess,sys
root=Path('C:/u4y'); platform=root/'검증 설치/hardware/nucode/zephyr'
spec=importlib.util.spec_from_file_location('installed_diagnostic_builder', platform/'tools/nu54-builder/src/nu54_builder.py'); builder=importlib.util.module_from_spec(spec);sys.modules[spec.name]=builder;spec.loader.exec_module(builder)
bundle=Path('C:/Users/eidos/ncs/toolchains/dcbdc366a1');ncs=Path('C:/Users/eidos/ncs/v3.4.0')
os.environ['PATH']=os.pathsep.join([str(Path(os.environ['SystemRoot'])/'System32'),os.environ['SystemRoot'],r'C:\Program Files\Git\cmd'])
os.environ.update(builder.apply_toolchain_environment(bundle))
os.environ.update({'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1','NUCODE_NCS_ROOT':str(ncs),'NUCODE_TOOLCHAIN_ROOT':str(bundle),'NUCODE_PYTHON':str(bundle/'opt/bin/python.exe'),'NUCODE_BUILD_CACHE_ROOT':str(root/'cache'),'CMAKE_BUILD_PARALLEL_LEVEL':'2','TEMP':str(root/'tmp'),'TMP':str(root/'tmp')})
cli=Path('C:/NU54DEV/tools/arduino-cli-1.5.1/arduino-cli.exe')
command=[str(cli),'--config-file',str(root/'arduino-cli.yaml'),'compile','--verbose','--fqbn','nucode:zephyr:nu54dk','--board-options','feature_set=ble','--build-path',str(root/'retry-gattperipheral'),str(platform/'libraries/NUCODE_BLE/examples/CustomGattPeripheral')]
result=subprocess.run(command,cwd=root)
print('RETRY_GATT_EXIT='+str(result.returncode),flush=True)
raise SystemExit(result.returncode)
