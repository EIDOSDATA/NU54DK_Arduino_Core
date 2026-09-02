cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_arduino_wire_pmic_id)

target_sources(app PRIVATE src/wire_pmic_id.cpp)
