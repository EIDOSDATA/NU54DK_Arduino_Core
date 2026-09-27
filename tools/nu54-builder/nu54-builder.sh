#!/bin/sh
# Doxygen: NU54 Build Adapter의 POSIX Python 진입점입니다.
set -eu

PYTHONUTF8=1
PYTHONNOUSERSITE=1
export PYTHONUTF8 PYTHONNOUSERSITE
unset PYTHONHOME PYTHONPATH

nu54_python=""
if [ -n "${NUCODE_PYTHON:-}" ] && [ -x "${NUCODE_PYTHON}" ]; then
    nu54_python="${NUCODE_PYTHON}"
fi

if [ -z "${nu54_python}" ] && [ -n "${NUCODE_TOOLCHAIN_ROOT:-}" ]; then
    for candidate in \
        "${NUCODE_TOOLCHAIN_ROOT}/opt/bin/python3" \
        "${NUCODE_TOOLCHAIN_ROOT}/opt/bin/python"
    do
        if [ -x "${candidate}" ]; then
            nu54_python="${candidate}"
            break
        fi
    done
fi

if [ -z "${nu54_python}" ]; then
    for toolchain in "${HOME}/ncs/toolchains"/* /opt/nordic/ncs/toolchains/*
    do
        if [ ! -d "${toolchain}" ]; then
            continue
        fi
        for candidate in "${toolchain}/opt/bin/python3" "${toolchain}/opt/bin/python"
        do
            if [ -x "${candidate}" ]; then
                nu54_python="${candidate}"
                break 2
            fi
        done
    done
fi

if [ -z "${nu54_python}" ]; then
    echo "nu54-builder: bundled Python executable was not found." >&2
    exit 2
fi

launcher_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "${nu54_python}" -I "${launcher_directory}/src/nu54_builder.py" "$@"
