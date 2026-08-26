/**
 * @file ArduinoRuntime.h
 * @brief Core 내부 런타임 확장 지점의 비공개 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_INTERNAL_ARDUINO_RUNTIME_H_
#define NUCODE_ARDUINO_CORE_INTERNAL_ARDUINO_RUNTIME_H_

/**
 * @brief 보드 Variant별 선행 초기화를 수행합니다.
 *
 * M2에서는 약한 no-op 구현을 제공하며, 이후 단계의 Variant가 강한 심볼로
 * 재정의할 수 있습니다. Sketch 공개 API가 아니므로 직접 호출하지 않습니다.
 *
 * @note 보드별 구현은 Core 기본 구현과 같은 C++ 함수 계약을 사용합니다.
 */
void initVariant(void);

#endif
