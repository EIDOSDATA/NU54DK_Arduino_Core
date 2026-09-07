/** @file @brief Fixture 501의 입력 및 단일 오픈드레인 LOW 결선 검사입니다. */
#pragma once
#include <cstdint>

/** @brief 부팅 시 공통 결선의 모든 신호를 입력으로 분리합니다. */
void initializeWiringIdle();
/** @brief 출력 pulse와 fixture lease 만료를 처리합니다. */
void serviceWiring();
/** @brief 결선 checker가 다른 HIL 모드를 차단하는지 반환합니다. */
bool wiringClaimed();
/** @brief 고정 net 명령만 처리하며 임의 GPIO 주소를 허용하지 않습니다. */
std::uint32_t wiringCommand(std::uint32_t opcode, const std::uint32_t *args, std::uint32_t nargs,
                            std::uint32_t *out, std::uint32_t &count);
