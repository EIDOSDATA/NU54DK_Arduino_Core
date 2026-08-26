cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})

# NCS security CMake가 남기는 string cache가 다음 configure에서 Kconfig override로
# 오인되지 않도록 application scope에서 제거한다.
unset(CONFIG_MBEDTLS_CONFIG_FILE CACHE)
unset(CONFIG_TF_PSA_CRYPTO_CONFIG_FILE CACHE)
unset(CONFIG_TF_PSA_CRYPTO_USER_CONFIG_FILE CACHE)

project(nucode_arduino_sketch)

# 최초 configure-only에서도 Zephyr app target이 유효하도록 항상 bootstrap을 둔다.
target_sources(app PRIVATE src/bootstrap.cpp)

# Build Adapter가 원자적으로 갱신하며, 실제 sketch/library source는 Zephyr가 컴파일한다.
include("${CMAKE_CURRENT_SOURCE_DIR}/sources.cmake")

if(NUCODE_ARDUINO_SKETCH_SOURCES)
  target_sources(app PRIVATE ${NUCODE_ARDUINO_SKETCH_SOURCES})
endif()

if(NUCODE_ARDUINO_INCLUDE_DIRS)
  target_include_directories(app PRIVATE ${NUCODE_ARDUINO_INCLUDE_DIRS})
endif()
