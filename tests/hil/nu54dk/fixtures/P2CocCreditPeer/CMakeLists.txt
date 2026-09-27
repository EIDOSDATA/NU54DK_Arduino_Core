cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(p2_coc_credit_peer)

target_sources(app PRIVATE src/main.c)
