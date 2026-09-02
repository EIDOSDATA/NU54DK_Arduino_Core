# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_m6_core_api)

target_sources(app PRIVATE
  src/c_header_contract.c
  src/main.cpp
)
