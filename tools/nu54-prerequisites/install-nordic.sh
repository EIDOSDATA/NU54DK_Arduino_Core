#!/bin/sh
## @brief OS 공통 Python prerequisite backend에 인자를 그대로 전달합니다.
set -eu
prerequisite_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "${NUCODE_PYTHON:-python3}" -I "${prerequisite_directory}/nordic.py" install "$@"
