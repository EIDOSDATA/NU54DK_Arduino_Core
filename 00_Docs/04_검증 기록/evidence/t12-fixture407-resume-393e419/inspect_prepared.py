"""! @brief 준비된 두 image의 exact identity를 파일에서 확인하며 보드를 구동하지 않습니다. """
from runtime import *
import v04_pair as pair

images = [pair.inspect_image(REPO, BUILD, role) for role in (1, 2)]
assert all(item['core_revision'] == SOURCE for item in images)
write_new(WORK / 'prepared-images.json', [{key: str(value) if isinstance(value, Path) else value
    for key, value in item.items()} for item in images])
print('PREPARED_IMAGE_IDENTITY_PASS=2;PHYSICAL_NOT_RUN')
