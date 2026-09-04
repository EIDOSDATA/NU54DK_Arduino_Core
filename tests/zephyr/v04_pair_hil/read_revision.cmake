# SPDX-License-Identifier: MIT
find_package(Git REQUIRED)
function(nucode_hil_revision core_root output_variable)
  file(REAL_PATH "${core_root}" exact_root)
  # Same narrowly scoped trust as zephyr/CMakeLists.txt. Container checkout
  # ownership can differ; do not change global config or trust arbitrary roots.
  execute_process(COMMAND "${GIT_EXECUTABLE}" -c "safe.directory=${exact_root}"
                          -C "${exact_root}" rev-parse HEAD
                  RESULT_VARIABLE revision_result OUTPUT_VARIABLE revision
                  ERROR_VARIABLE revision_error OUTPUT_STRIP_TRAILING_WHITESPACE)
  string(LENGTH "${revision}" revision_length)
  if(NOT revision_result EQUAL 0 OR NOT revision_length EQUAL 40 OR
     NOT revision MATCHES "^[0-9a-f]+$")
    message(FATAL_ERROR "Cannot determine exact HIL source revision: ${revision_error}")
  endif()
  set(${output_variable} "${revision}" PARENT_SCOPE)
endfunction()
