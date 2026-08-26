set(NUCODE_BUILD_RECORD
  "${CMAKE_BINARY_DIR}/nucode_arduino_core_build.yml"
)

if(CONFIG_NUCODE_ARDUINO_CORE)
  get_filename_component(NUCODE_ARDUINO_CORE_ROOT
    "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE
  )

  if(NOT CONFIG_BOARD_NRF54L15DK_NRF54L15_CPUAPP_NU54DK)
    message(FATAL_ERROR
      "NUCODE Arduino Core M3 currently requires the NU54DK board variant"
    )
  endif()

  set(NUCODE_ARDUINO_VARIANT_ROOT
    "${NUCODE_ARDUINO_CORE_ROOT}/variants/nu54dk"
  )

  set(NUCODE_ARDUINO_CORE_SOURCES
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/main.cpp"
  )

  if(CONFIG_NUCODE_ARDUINO_GPIO)
    list(APPEND NUCODE_ARDUINO_CORE_SOURCES
      "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/wiring_digital.cpp"
      "${NUCODE_ARDUINO_VARIANT_ROOT}/variant.cpp"
    )
  endif()

  if(CONFIG_NUCODE_ARDUINO_TIME)
    list(APPEND NUCODE_ARDUINO_CORE_SOURCES
      "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/wiring_time.cpp"
      "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/internal/time_backend_nrf54.cpp"
    )
  endif()

  zephyr_library_named(nucode_arduino_core)
  zephyr_library_sources(${NUCODE_ARDUINO_CORE_SOURCES})
  zephyr_include_directories(
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino"
    "${NUCODE_ARDUINO_VARIANT_ROOT}"
  )

  find_package(Git QUIET)

  function(nucode_git_revision directory output_variable check_dirty)
    set(revision "unknown")

    if(GIT_FOUND AND EXISTS "${directory}")
      execute_process(
        COMMAND "${GIT_EXECUTABLE}" rev-parse --short=12 HEAD
        WORKING_DIRECTORY "${directory}"
        RESULT_VARIABLE git_result
        OUTPUT_VARIABLE git_output
        ERROR_QUIET
        OUTPUT_STRIP_TRAILING_WHITESPACE
      )

      if(git_result EQUAL 0 AND NOT "${git_output}" STREQUAL "")
        set(revision "${git_output}")

        if(check_dirty)
          execute_process(
            COMMAND "${GIT_EXECUTABLE}" diff --quiet HEAD -- ${ARGN}
            WORKING_DIRECTORY "${directory}"
            RESULT_VARIABLE git_diff_result
            ERROR_QUIET
          )

          execute_process(
            COMMAND "${GIT_EXECUTABLE}" ls-files --others --exclude-standard -- ${ARGN}
            WORKING_DIRECTORY "${directory}"
            RESULT_VARIABLE git_untracked_result
            OUTPUT_VARIABLE git_untracked_output
            ERROR_QUIET
            OUTPUT_STRIP_TRAILING_WHITESPACE
          )

          if(git_diff_result EQUAL 1 OR
             (git_untracked_result EQUAL 0 AND
              NOT "${git_untracked_output}" STREQUAL ""))
            string(APPEND revision "-dirty")
          endif()
        endif()
      endif()
    endif()

    set(${output_variable} "${revision}" PARENT_SCOPE)
  endfunction()

  function(nucode_files_digest base_directory output_variable)
    set(digest_input "")

    foreach(input_file IN LISTS ARGN)
      if(EXISTS "${input_file}" AND NOT IS_DIRECTORY "${input_file}")
        file(SHA256 "${input_file}" input_hash)
        file(RELATIVE_PATH relative_path "${base_directory}" "${input_file}")
        string(REPLACE "\\" "/" relative_path "${relative_path}")
        string(APPEND digest_input "${relative_path}:${input_hash}\n")
      endif()
    endforeach()

    if("${digest_input}" STREQUAL "")
      set(digest "unknown")
    else()
      string(SHA256 digest "${digest_input}")
    endif()

    set(${output_variable} "${digest}" PARENT_SCOPE)
  endfunction()

  set(NUCODE_BOARD_PACKAGE_ROOT "")
  foreach(board_directory IN LISTS BOARD_DIRECTORIES)
    string(REPLACE "\\" "/" normalized_board_directory "${board_directory}")
    if(normalized_board_directory MATCHES "/boards/nucode/nu54dk$" AND
       EXISTS "${board_directory}/board.cmake")
      get_filename_component(NUCODE_BOARD_PACKAGE_ROOT
        "${board_directory}/../../.." ABSOLUTE
      )
      break()
    endif()
  endforeach()

  if("${NUCODE_BOARD_PACKAGE_ROOT}" STREQUAL "")
    foreach(board_root IN LISTS BOARD_ROOT)
      if(EXISTS "${board_root}/boards/nucode/nu54dk")
        get_filename_component(NUCODE_BOARD_PACKAGE_ROOT
          "${board_root}" ABSOLUTE
        )
        break()
      endif()
    endforeach()
  endif()

  file(GLOB_RECURSE NUCODE_CORE_BUILD_INPUTS
    LIST_DIRECTORIES FALSE
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/*"
    "${NUCODE_ARDUINO_CORE_ROOT}/variants/nu54dk/*"
    "${NUCODE_ARDUINO_CORE_ROOT}/zephyr/*"
  )
  list(SORT NUCODE_CORE_BUILD_INPUTS)

  file(GLOB_RECURSE NUCODE_APPLICATION_BUILD_INPUTS
    LIST_DIRECTORIES FALSE
    "${APPLICATION_SOURCE_DIR}/*"
  )
  list(SORT NUCODE_APPLICATION_BUILD_INPUTS)

  set(NUCODE_BOARD_BUILD_INPUTS)
  if(NOT "${NUCODE_BOARD_PACKAGE_ROOT}" STREQUAL "")
    file(GLOB_RECURSE NUCODE_BOARD_BUILD_INPUTS
      LIST_DIRECTORIES FALSE
      "${NUCODE_BOARD_PACKAGE_ROOT}/boards/nucode/nu54dk/*"
    )
    list(SORT NUCODE_BOARD_BUILD_INPUTS)
  endif()

  nucode_git_revision(
    "${NUCODE_ARDUINO_CORE_ROOT}" NUCODE_CORE_REVISION TRUE
    cores variants zephyr
  )
  nucode_git_revision(
    "${NUCODE_BOARD_PACKAGE_ROOT}" NUCODE_BOARD_REVISION TRUE
    boards/nucode/nu54dk
  )
  nucode_git_revision("${NRF_DIR}" NUCODE_NCS_REVISION FALSE)
  nucode_git_revision("${ZEPHYR_BASE}" NUCODE_ZEPHYR_REVISION FALSE)

  nucode_files_digest(
    "${NUCODE_ARDUINO_CORE_ROOT}" NUCODE_CORE_SOURCE_SHA256
    ${NUCODE_CORE_BUILD_INPUTS}
  )
  nucode_files_digest(
    "${APPLICATION_SOURCE_DIR}" NUCODE_APPLICATION_SOURCE_SHA256
    ${NUCODE_APPLICATION_BUILD_INPUTS}
  )
  nucode_files_digest(
    "${NUCODE_BOARD_PACKAGE_ROOT}" NUCODE_BOARD_SOURCE_SHA256
    ${NUCODE_BOARD_BUILD_INPUTS}
  )

  build_info(vendor-specific nucode-arduino-core core-revision
    VALUE "${NUCODE_CORE_REVISION}"
  )
  build_info(vendor-specific nucode-arduino-core core-source-sha256
    VALUE "${NUCODE_CORE_SOURCE_SHA256}"
  )
  build_info(vendor-specific nucode-arduino-core application-source-sha256
    VALUE "${NUCODE_APPLICATION_SOURCE_SHA256}"
  )
  build_info(vendor-specific nucode-arduino-core board-package-revision
    VALUE "${NUCODE_BOARD_REVISION}"
  )
  build_info(vendor-specific nucode-arduino-core board-source-sha256
    VALUE "${NUCODE_BOARD_SOURCE_SHA256}"
  )
  build_info(vendor-specific nucode-arduino-core ncs-revision
    VALUE "${NUCODE_NCS_REVISION}"
  )
  build_info(vendor-specific nucode-arduino-core zephyr-revision
    VALUE "${NUCODE_ZEPHYR_REVISION}"
  )
  build_info(vendor-specific nucode-arduino-core cxx-compiler
    VALUE "${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}"
  )

  set(NUCODE_BUILD_RECORD_SCRIPT
    "${CMAKE_CURRENT_LIST_DIR}/cmake/write_build_record.cmake"
  )

  add_custom_target(nucode_arduino_core_build_record ALL
    COMMAND "${CMAKE_COMMAND}"
      "-DNUCODE_CORE_ROOT=${NUCODE_ARDUINO_CORE_ROOT}"
      "-DNUCODE_APPLICATION_SOURCE_DIR=${APPLICATION_SOURCE_DIR}"
      "-DNUCODE_BOARD_PACKAGE_ROOT=${NUCODE_BOARD_PACKAGE_ROOT}"
      "-DNUCODE_NRF_DIR=${NRF_DIR}"
      "-DNUCODE_ZEPHYR_BASE=${ZEPHYR_BASE}"
      "-DNUCODE_GIT_EXECUTABLE=${GIT_EXECUTABLE}"
      "-DNUCODE_BUILD_RECORD=${NUCODE_BUILD_RECORD}"
      "-DNUCODE_BOARD=${BOARD}"
      "-DNUCODE_BOARD_QUALIFIERS=${BOARD_QUALIFIERS}"
      "-DNUCODE_TOOLCHAIN_VARIANT=${ZEPHYR_TOOLCHAIN_VARIANT}"
      "-DNUCODE_TOOLCHAIN_PATH=${ZEPHYR_SDK_INSTALL_DIR}"
      "-DNUCODE_CXX_COMPILER=${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}"
      -P "${NUCODE_BUILD_RECORD_SCRIPT}"
    BYPRODUCTS "${NUCODE_BUILD_RECORD}"
    VERBATIM
  )

  message(STATUS
    "NUCODE Arduino Core ${NUCODE_CORE_REVISION}; "
    "NU54DK board ${NUCODE_BOARD_REVISION}"
  )
else()
  file(REMOVE "${NUCODE_BUILD_RECORD}")
endif()
