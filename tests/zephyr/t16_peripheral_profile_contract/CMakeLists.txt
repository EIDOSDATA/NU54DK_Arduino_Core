cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(t16_peripheral_profile_contract LANGUAGES C CXX)

target_include_directories(
    app
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/../../../libraries/NUCODE_Peripheral_Fabric/src
)
target_sources(app PRIVATE src/main.cpp)
