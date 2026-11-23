## @brief 병렬 Twister 구성의 toolchain cache를 각 binary directory 안에 격리합니다.
if(NOT DEFINED APPLICATION_BINARY_DIR OR NOT IS_ABSOLUTE "${APPLICATION_BINARY_DIR}")
    message(FATAL_ERROR "Twister cache isolation requires an absolute APPLICATION_BINARY_DIR")
endif()

## @note SDK·사용자 공용 cache를 수정하지 않고 빌드 원본과 함께 보존합니다.
set(USER_CACHE_DIR "${APPLICATION_BINARY_DIR}/.cache"
    CACHE PATH "Isolated Twister configuration cache" FORCE)
set(ZEPHYR_TOOLCHAIN_CAPABILITY_CACHE_DIR "${USER_CACHE_DIR}/ToolchainCapabilityDatabase"
    CACHE PATH "Isolated Twister toolchain capability cache" FORCE)
