/**
 * @file LocalAccumulator.cpp
 * @brief local Arduino library dependency 연결 구현입니다.
 */

#include "LocalAccumulator.h"

#include <LeafValue.h>

/** @brief 입력과 dependency 값을 더합니다. */
int localAccumulate(int value)
{
  return value + leafValue();
}
