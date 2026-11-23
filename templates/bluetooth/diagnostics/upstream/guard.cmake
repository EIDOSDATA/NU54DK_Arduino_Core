# SPDX-License-Identifier: MIT
# 고정 SDK의 파일은 수정하지 않고 application 진입점에 유한 watchdog guard를 결합한다.
if(TARGET app AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/src/main.c")
    get_target_property(guard_added app NUCODE_DIAGNOSTIC_GUARD)
    if(NOT guard_added)
        set_source_files_properties("${CMAKE_CURRENT_SOURCE_DIR}/src/main.c"
            PROPERTIES COMPILE_DEFINITIONS "main=nucode_upstream_main")
        target_sources(app PRIVATE "${CMAKE_CURRENT_LIST_DIR}/../controller/src/main.c")
        target_compile_definitions(app PRIVATE NUCODE_DIAGNOSTIC_HOST_APP=1)
        set_target_properties(app PROPERTIES NUCODE_DIAGNOSTIC_GUARD TRUE)
    endif()
endif()
