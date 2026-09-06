"""! @brief 검증된 405 감사 틀에서 406의 독립 oracle과 build 경계를 구성합니다. """
from pathlib import Path
import shutil

work = Path(__file__).resolve().parent
prior = work.parent / 't12-fixture405'

def replace(text, old, new):
    assert old in text, old
    return text.replace(old, new)

text = (prior / 'audit_results.py').read_text(encoding='utf-8').replace('405', '406')
text = replace(text, "result['fixture_revision'] == 3", "result['fixture_revision'] == 4")
text = replace(text, 'open-drain-shared-ain4-manual-saadc', 'input-bias-shared-ain5-manual-saadc')
text = replace(text, 'sum(value > 256 for value in samples)', 'sum(value > 1024 for value in samples)')
text = replace(text, "row['high_samples'] * 100 >= len(samples) * 95 and row['median'] > 256", "row['high_samples'] == len(samples) and row['median'] > 1024")
text = replace(text, 'max(samples) <= 256', 'max(samples) <= 512')
text = replace(text, "['low-before', 'released', 'low-after']", "['pulldown-before', 'pullup', 'pulldown-after']")
text = replace(text, '[1, phase, 46, 1, 1, 1, int(phase == 1)]', '[1, phase, 46, 0, int(phase == 1), 0, 1]')
text = replace(text, 'row[key][8] & 0xF0F == 0x80D', 'row[key][8] & 0xF0F == (0xC if phase == 1 else 0x4)')
text = replace(text, "group[2]['median']) + 256", "group[2]['median']) + 512")
text = replace(text, 'source_open_drain_readbacks', 'source_input_bias_readbacks')
text = replace(text, 'AIN4 PMIC_INT shared input LOW/release/LOW, static open-drain, single/double SAADC DMA and cleanup',
               'AIN5 VBAT_MON shared input INPUT pulldown/pullup/pulldown, single/double SAADC DMA and cleanup')
text = replace(text, "'PMIC interrupt generation or register behavior', 'SB1 continuity'", "'battery voltage or PMIC register behavior', 'SB4 continuity'")
text = replace(text, 'Fixture 406/407/408 and later T12', 'Fixture 407/408 and later T12')
(work / 'audit_results.py').write_text(text, encoding='utf-8', newline='\n')

text = (prior / 'collect_build.py').read_text(encoding='utf-8')
text = replace(text, 'C:\\u3l', 'C:\\u3m')
text = replace(text, 'r13/u3l-artifact-index.json', 'r13/u3m-artifact-index.json')
text = replace(text, 't12-fixture404/target-artifact-index.json', 't12-fixture405/target-artifact-index.json')
text = replace(text, "['tests/zephyr/v04_pair_hil/src/main.cpp', 'tests/zephyr/v04_pair_hil/src/signal_hil.cpp']", "['tests/zephyr/v04_pair_hil/src/signal_hil.cpp']")
text = replace(text, 'e080bbc8f07a0ad751d83dacdb259d395b69be5b', '9fc12bfbdafbb8a4450ed6cc61ca97b9c1efd220')
text = replace(text, 'prior_fixture404_source', 'prior_fixture405_source')
text = replace(text, '405 must run on these new images', '406 must run on these new images')
(work / 'collect_build.py').write_text(text, encoding='utf-8', newline='\n')

text = (prior / 'publish_evidence.py').read_text(encoding='utf-8').replace('405', '406').replace('gate-host-final.log', 'gate-host.log')
(work / 'publish_evidence.py').write_text(text, encoding='utf-8', newline='\n')
shutil.copyfile(work.parent / 'prepare406.py', work / 'authoring_prepare406.py')
print('FIXTURE406_INDEPENDENT_AUDITS_PREPARED')
