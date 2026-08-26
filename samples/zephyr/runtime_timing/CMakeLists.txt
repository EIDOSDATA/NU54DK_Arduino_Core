cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nu54_runtime_timing)

target_sources(app PRIVATE src/runtime_timing.cpp)
