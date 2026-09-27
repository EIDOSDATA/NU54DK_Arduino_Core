# SPDX-License-Identifier: MIT

# @brief M30 전원 HIL build에만 MCUboot swap 관찰 훅을 추가합니다.
if("${M30_DFU_POWER_HIL}" STREQUAL "1")
  list(APPEND mcuboot_EXTRA_CONF_FILE
    "${CMAKE_CURRENT_LIST_DIR}/sysbuild/mcuboot-power.conf"
  )
  list(REMOVE_DUPLICATES mcuboot_EXTRA_CONF_FILE)
  set(mcuboot_EXTRA_CONF_FILE "${mcuboot_EXTRA_CONF_FILE}" CACHE INTERNAL "")
endif()
