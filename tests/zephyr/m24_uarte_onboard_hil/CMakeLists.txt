cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(m24uh LANGUAGES C CXX)

target_sources(app PRIVATE src/main.cpp)
