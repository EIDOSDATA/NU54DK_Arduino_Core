cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_arduino_spi_transaction)

target_sources(app PRIVATE src/spi_transaction.cpp)
