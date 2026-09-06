"""! @brief Host C/C++ 시험의 명시적 컴파일러와 인자를 선택합니다. """

import json
import os
import shutil


def compiler_command(language="c++", optional=False):
    """! @brief 명시한 도구가 없으면 실패하며 셸 없이 실행할 인자 목록을 반환합니다. """
    if language not in ("c", "c++"):
        raise ValueError("Host compiler language must be c or c++")
    variable = "CXX" if language == "c++" else "CC"
    explicit = os.environ.get(variable)
    defaults = ("g++", "clang++", "c++") if language == "c++" else ("gcc", "clang", "cc")
    candidates = (explicit,) if explicit else defaults
    compiler = next((path for candidate in candidates if (path := shutil.which(candidate))), None)
    if compiler is None:
        if optional and not explicit:
            return None
        raise AssertionError(f"Host {variable} compiler unavailable: {candidates}")
    flags_variable = f"NUCODE_HOST_{variable}_FLAGS"
    try:
        flags = json.loads(os.environ.get(flags_variable, "[]"))
    except json.JSONDecodeError as error:
        raise AssertionError(f"{flags_variable} must be a JSON string array") from error
    if not isinstance(flags, list) or not all(isinstance(flag, str) for flag in flags):
        raise AssertionError(f"{flags_variable} must be a JSON string array")
    return [compiler, *flags]
