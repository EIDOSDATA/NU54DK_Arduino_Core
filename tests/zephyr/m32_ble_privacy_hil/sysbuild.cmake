# SPDX-License-Identifier: MIT

# Filter Accept List에 등록한 exact identity로 연결하도록 peer의 RPA 사용을 끕니다.
if("${M32_PRIV_ROLE}" STREQUAL "peer")
    set_config_bool(${DEFAULT_IMAGE} CONFIG_BT_PRIVACY n)
    set_config_bool(${DEFAULT_IMAGE} CONFIG_BT_RPA_TIMEOUT_DYNAMIC n)
    set_config_bool(${DEFAULT_IMAGE} CONFIG_BT_SCAN_WITH_IDENTITY y)
endif()
