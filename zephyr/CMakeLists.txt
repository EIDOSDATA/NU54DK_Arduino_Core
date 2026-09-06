set(NUCODE_BUILD_RECORD
  "${CMAKE_BINARY_DIR}/nucode_arduino_core_build.yml"
)

if(CONFIG_NUCODE_ARDUINO_CORE)
  get_filename_component(NUCODE_ARDUINO_CORE_ROOT
    "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE
  )
  include("${CMAKE_CURRENT_LIST_DIR}/cmake/product_identity.cmake")
  nucode_product_identity("${NUCODE_ARDUINO_CORE_ROOT}"
    NUCODE_CORE_SOURCE_VERSION NUCODE_PACKAGE_VERSION
  )
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino/internal/CoreIdentity.h"
    "${NUCODE_ARDUINO_CORE_ROOT}/platform.txt"
  )

  if(NOT CONFIG_BOARD_NRF54L15DK_NRF54L15_CPUAPP_NU54DK)
    message(FATAL_ERROR
      "NUCODE Arduino Core currently requires the NU54DK board variant"
    )
  endif()

  set(NUCODE_ARDUINO_VARIANT_ROOT
    "${NUCODE_ARDUINO_CORE_ROOT}/variants/nu54dk"
  )
  set(NUCODE_ARDUINO_API_ROOT
    "${NUCODE_ARDUINO_CORE_ROOT}/third_party/ArduinoCore-API"
  )

  if(NOT EXISTS "${NUCODE_ARDUINO_API_ROOT}/api/ArduinoAPI.h")
    message(FATAL_ERROR
      "Vendored ArduinoCore-API 1.5.2 is missing; this Core checkout or package is incomplete"
    )
  endif()

  include("${CMAKE_CURRENT_LIST_DIR}/cmake/source_selection.cmake")

  zephyr_library_named(nucode_arduino_core)
  zephyr_library_sources(${NUCODE_ARDUINO_CORE_SOURCES})
  zephyr_include_directories(
    "${NUCODE_ARDUINO_CORE_ROOT}/cores/arduino"
    "${NUCODE_ARDUINO_CORE_ROOT}/dts"
    "${NUCODE_ARDUINO_VARIANT_ROOT}"
  )
  zephyr_system_include_directories(
    "${NUCODE_ARDUINO_API_ROOT}"
  )

  include("${CMAKE_CURRENT_LIST_DIR}/cmake/source_provenance.cmake")

  include("${CMAKE_CURRENT_LIST_DIR}/cmake/build_record_target.cmake")
else()
  file(REMOVE "${NUCODE_BUILD_RECORD}")
endif()
