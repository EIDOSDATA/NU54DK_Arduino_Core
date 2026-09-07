/**
 * @file pwm_capture_hil.h
 * @brief Fixture 408의 PWM 출력과 다른 보드 TIMER capture를 준비합니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <cstdint>

/** @brief PWM capture fixture의 만료를 확인하고 STOP 뒤 자원을 반환합니다. */
void servicePwmCapture();
/** @brief 준비·실행·정지 실패를 포함한 fixture 점유 여부입니다. */
bool pwmCaptureClaimed();
/** @brief 유한 peer capture가 실행 중이면 main loop를 짧게 유지합니다. */
bool pwmCaptureNeedsPolling();
/** @brief 현재 결선 허가 안에서만 고정 P1.14 경로를 제어합니다. */
std::uint32_t pwmCaptureCommand(std::uint32_t opcode, const std::uint32_t *args,
                                std::uint32_t nargs, std::uint32_t *out, std::uint32_t &count);
