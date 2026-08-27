cmake_minimum_required(VERSION 3.20.0)

function(nucode_git_revision directory output_variable check_dirty)
  set(revision "unknown")

  if(EXISTS "${NUCODE_GIT_EXECUTABLE}" AND EXISTS "${directory}")
    execute_process(
      COMMAND "${NUCODE_GIT_EXECUTABLE}" rev-parse --show-toplevel
      WORKING_DIRECTORY "${directory}"
      RESULT_VARIABLE git_root_result
      OUTPUT_VARIABLE git_root_output
      ERROR_QUIET
      OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    file(REAL_PATH "${directory}" requested_root)
    file(TO_CMAKE_PATH "${requested_root}" requested_root)
    file(TO_CMAKE_PATH "${git_root_output}" git_root_output)
    if(WIN32)
      string(TOLOWER "${requested_root}" requested_root)
      string(TOLOWER "${git_root_output}" git_root_output)
    endif()

    if(git_root_result EQUAL 0 AND "${git_root_output}" STREQUAL "${requested_root}")
      execute_process(
        COMMAND "${NUCODE_GIT_EXECUTABLE}" rev-parse --short=12 HEAD
        WORKING_DIRECTORY "${directory}"
        RESULT_VARIABLE git_result
        OUTPUT_VARIABLE git_output
        ERROR_QUIET
        OUTPUT_STRIP_TRAILING_WHITESPACE
      )
    else()
      set(git_result 1)
    endif()

    if(git_result EQUAL 0 AND NOT "${git_output}" STREQUAL "")
      set(revision "${git_output}")

      if(check_dirty)
        execute_process(
          COMMAND "${NUCODE_GIT_EXECUTABLE}" diff --quiet HEAD -- ${ARGN}
          WORKING_DIRECTORY "${directory}"
          RESULT_VARIABLE git_diff_result
          ERROR_QUIET
        )
        execute_process(
          COMMAND "${NUCODE_GIT_EXECUTABLE}" ls-files --others
                  --exclude-standard -- ${ARGN}
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

# @brief Git metadata가 없는 배포 archive에서 고정 revision을 읽습니다.
function(nucode_release_manifest_revision field output_variable)
  set(revision "unknown")
  set(manifest "${NUCODE_CORE_ROOT}/release-manifest.json")
  if(EXISTS "${manifest}")
    file(READ "${manifest}" manifest_content)
    string(JSON manifest_revision ERROR_VARIABLE manifest_error
      GET "${manifest_content}" "${field}"
    )
    if("${manifest_error}" STREQUAL "NOTFOUND" AND
       "${manifest_revision}" MATCHES "^[0-9a-fA-F]{40}$")
      string(TOLOWER "${manifest_revision}" revision)
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

function(nucode_yaml_quote input output_variable)
  string(REPLACE "'" "''" quoted "${input}")
  set(${output_variable} "'${quoted}'" PARENT_SCOPE)
endfunction()

file(GLOB_RECURSE core_inputs
  LIST_DIRECTORIES FALSE
  "${NUCODE_CORE_ROOT}/cores/arduino/*"
  "${NUCODE_CORE_ROOT}/dts/*"
  "${NUCODE_CORE_ROOT}/libraries/*"
  "${NUCODE_CORE_ROOT}/third_party/ArduinoCore-API/*"
  "${NUCODE_CORE_ROOT}/third_party/ArduinoCore-API.provenance.yml"
  "${NUCODE_CORE_ROOT}/variants/nu54dk/*"
  "${NUCODE_CORE_ROOT}/zephyr/*"
)
list(SORT core_inputs)

file(GLOB_RECURSE board_inputs
  LIST_DIRECTORIES FALSE
  "${NUCODE_BOARD_PACKAGE_ROOT}/boards/nucode/nu54dk/*"
)
list(SORT board_inputs)

file(GLOB_RECURSE application_inputs
  LIST_DIRECTORIES FALSE
  "${NUCODE_APPLICATION_SOURCE_DIR}/*"
)
list(SORT application_inputs)

nucode_git_revision(
  "${NUCODE_CORE_ROOT}" core_revision TRUE
  cores dts libraries third_party variants zephyr
)
nucode_git_revision(
  "${NUCODE_BOARD_PACKAGE_ROOT}" board_revision TRUE boards/nucode/nu54dk
)
nucode_git_revision("${NUCODE_NRF_DIR}" ncs_revision FALSE)
nucode_git_revision("${NUCODE_ZEPHYR_BASE}" zephyr_revision FALSE)
if("${core_revision}" STREQUAL "unknown")
  nucode_release_manifest_revision(core_revision core_revision)
endif()
if("${board_revision}" STREQUAL "unknown")
  nucode_release_manifest_revision(board_revision board_revision)
endif()
nucode_files_digest("${NUCODE_CORE_ROOT}" core_source_sha256 ${core_inputs})
nucode_files_digest(
  "${NUCODE_APPLICATION_SOURCE_DIR}" application_source_sha256
  ${application_inputs}
)
nucode_files_digest(
  "${NUCODE_BOARD_PACKAGE_ROOT}" board_source_sha256 ${board_inputs}
)

foreach(variable IN ITEMS
    core_revision
    core_source_sha256
    application_source_sha256
    board_revision
    board_source_sha256
    ncs_revision
    zephyr_revision
    NUCODE_BOARD
    NUCODE_BOARD_QUALIFIERS
    NUCODE_TOOLCHAIN_VARIANT
    NUCODE_TOOLCHAIN_PATH
    NUCODE_CXX_COMPILER)
  nucode_yaml_quote("${${variable}}" "${variable}_yaml")
endforeach()

string(CONCAT build_record_content
  "nucode_arduino_core:\n"
  "  core_revision: ${core_revision_yaml}\n"
  "  core_source_sha256: ${core_source_sha256_yaml}\n"
  "  application_source_sha256: ${application_source_sha256_yaml}\n"
  "  board_revision: ${board_revision_yaml}\n"
  "  board_source_sha256: ${board_source_sha256_yaml}\n"
  "  ncs_revision: ${ncs_revision_yaml}\n"
  "  zephyr_revision: ${zephyr_revision_yaml}\n"
  "  board: ${NUCODE_BOARD_yaml}\n"
  "  board_qualifiers: ${NUCODE_BOARD_QUALIFIERS_yaml}\n"
  "  toolchain_variant: ${NUCODE_TOOLCHAIN_VARIANT_yaml}\n"
  "  toolchain_path: ${NUCODE_TOOLCHAIN_PATH_yaml}\n"
  "  cxx_compiler: ${NUCODE_CXX_COMPILER_yaml}\n"
)

set(build_record_temporary "${NUCODE_BUILD_RECORD}.tmp")
file(WRITE "${build_record_temporary}" "${build_record_content}")
configure_file(
  "${build_record_temporary}" "${NUCODE_BUILD_RECORD}" COPYONLY
)
file(REMOVE "${build_record_temporary}")
