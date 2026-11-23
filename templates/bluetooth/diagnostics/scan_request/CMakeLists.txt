# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_scan_request)
target_sources(app PRIVATE src/main.c ../controller/src/main.c)
target_compile_definitions(app PRIVATE NUCODE_DIAGNOSTIC_HOST_APP=1)
