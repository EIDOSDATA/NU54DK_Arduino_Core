# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_ac02b_hil_peer)

target_sources(app PRIVATE
  src/main.cpp
)
