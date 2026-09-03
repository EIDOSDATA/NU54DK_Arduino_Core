/**
 * @file main.cpp
 * @brief M23 identity API와 multi-instance/DMA 공통 소유권 의미를 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <nucode/PeripheralInventory.h>

#include "internal/IoResourceManager.h"

#include <zephyr/ztest.h>

#include <cstdint>
#include <string.h>

namespace
{
	using namespace nucode::arduino;
	using namespace nucode::arduino::internal;

	std::uint8_t peripheral_domain_a;
	std::uint8_t peripheral_domain_b;
	alignas(4) std::uint8_t dma_buffer[128]{};

	[[nodiscard]] IoResourceResult claim(IoResourceOwner owner,
										 const IoResourceId &resource,
										 IoResourceLease &lease) noexcept
	{
		const auto reserved = reserveIoResources(
			owner, &resource, 1U, IoAcquirePolicy::exclusive, lease);
		return reserved == IoResourceResult::success
				   ? commitIoResources(lease)
				   : reserved;
	}
}

ZTEST(m23_inventory_contract, test_runtime_identity_has_no_fake_alias)
{
	const auto *const serial = findPeripheralByObject("Serial");
	const auto *const serial1 = findPeripheralByObject("Serial1");
	const auto *const wire = findPeripheralByObject("Wire");
	const auto *const spi = findPeripheralByObject("SPI");
	zassert_not_null(serial, "Serial identity가 없습니다.");
	zassert_not_null(serial1, "Serial1 identity가 없습니다.");
	zassert_not_null(wire, "Wire identity가 없습니다.");
	zassert_not_null(spi, "SPI identity가 없습니다.");
	zassert_equal(serial->instance, 20U, "Serial은 UARTE20이어야 합니다.");
	zassert_equal(serial1->instance, 30U, "Serial1은 UARTE30이어야 합니다.");
	zassert_equal(wire->instance, 22U, "Wire는 TWIM22여야 합니다.");
	zassert_equal(spi->instance, 0U, "SPI는 SPIM00이어야 합니다.");
	zassert_is_null(findPeripheralByObject("Serial2"), "가짜 Serial2 alias가 노출됐습니다.");
	zassert_equal(peripheralInventorySize(), 75U, "전 instance inventory 수가 바뀌었습니다.");
}

ZTEST(m23_inventory_contract, test_same_serial_block_is_exclusive)
{
	resetIoResourceManagerForTest();
	const auto block21 = peripheralIoResource(IoResourceKind::serial_block, 21U);
	IoResourceLease uart{};
	IoResourceLease spi{};
	zassert_equal(claim({IoOwnerKind::serial, 21U}, block21, uart),
				  IoResourceResult::success, "UARTE21 block 획득이 실패했습니다.");
	IoResourceSnapshot conflict{};
	zassert_equal(reserveIoResources({IoOwnerKind::spi, 21U}, &block21, 1U,
									 IoAcquirePolicy::exclusive, spi, &conflict),
				  IoResourceResult::conflict,
				  "같은 serial21의 SPIM personality가 동시에 획득됐습니다.");
	zassert_equal(conflict.owner.kind, IoOwnerKind::serial,
				  "충돌 진단이 기존 UARTE owner를 잃었습니다.");
	zassert_equal(releaseIoResources(uart), IoResourceResult::success,
				  "serial21 반환이 실패했습니다.");
}

ZTEST(m23_inventory_contract, test_different_blocks_and_full_dma_bundle_can_coexist)
{
	resetIoResourceManagerForTest();
	const IoResourceId first[] = {
		peripheralIoResource(IoResourceKind::serial_block, 21U),
		peripheralIoResource(IoResourceKind::dppi_channel, 3U, &peripheral_domain_a),
		peripheralIoResource(IoResourceKind::timer_channel, 1U, &peripheral_domain_a),
		dmaMemoryIoResource(&dma_buffer[0], 32U),
	};
	const IoResourceId second[] = {
		peripheralIoResource(IoResourceKind::serial_block, 22U),
		peripheralIoResource(IoResourceKind::dppi_channel, 4U, &peripheral_domain_b),
		peripheralIoResource(IoResourceKind::timer_channel, 2U, &peripheral_domain_b),
		dmaMemoryIoResource(&dma_buffer[32], 32U),
	};
	IoResourceLease first_lease{};
	IoResourceLease second_lease{};
	zassert_equal(reserveIoResources({IoOwnerKind::serial, 21U}, first, 4U,
									 IoAcquirePolicy::exclusive, first_lease),
				  IoResourceResult::success, "첫 DMA bundle reserve가 실패했습니다.");
	zassert_equal(commitIoResources(first_lease), IoResourceResult::success,
				  "첫 DMA bundle commit이 실패했습니다.");
	zassert_equal(reserveIoResources({IoOwnerKind::wire, 22U}, second, 4U,
									 IoAcquirePolicy::exclusive, second_lease),
				  IoResourceResult::success, "서로 다른 block의 동시 reserve가 실패했습니다.");
	zassert_equal(commitIoResources(second_lease), IoResourceResult::success,
				  "두 번째 DMA bundle commit이 실패했습니다.");
	zassert_equal(releaseIoResources(second_lease), IoResourceResult::success,
				  "두 번째 DMA bundle 반환이 실패했습니다.");
	zassert_equal(releaseIoResources(first_lease), IoResourceResult::success,
				  "첫 DMA bundle 반환이 실패했습니다.");
}

ZTEST(m23_inventory_contract, test_overlapping_dma_ranges_fail_closed)
{
	resetIoResourceManagerForTest();
	const auto whole = dmaMemoryIoResource(&dma_buffer[16], 48U);
	const auto overlap = dmaMemoryIoResource(&dma_buffer[32], 16U);
	const auto adjacent = dmaMemoryIoResource(&dma_buffer[64], 16U);
	IoResourceLease owner{};
	IoResourceLease contender{};
	IoResourceLease adjacent_lease{};
	zassert_equal(claim({IoOwnerKind::spi, 0U}, whole, owner),
				  IoResourceResult::success, "DMA range 준비가 실패했습니다.");
	zassert_equal(reserveIoResources({IoOwnerKind::wire, 21U}, &overlap, 1U,
									 IoAcquirePolicy::exclusive, contender),
				  IoResourceResult::conflict, "겹친 DMA range가 허용됐습니다.");
	zassert_equal(claim({IoOwnerKind::wire, 21U}, adjacent, adjacent_lease),
				  IoResourceResult::success, "인접한 비중첩 DMA range가 거부됐습니다.");
	zassert_equal(releaseIoResources(adjacent_lease), IoResourceResult::success,
				  "인접 DMA range 반환이 실패했습니다.");
	zassert_equal(releaseIoResources(owner), IoResourceResult::success,
				  "원래 DMA range 반환이 실패했습니다.");
}

ZTEST(m23_inventory_contract, test_invalid_dma_ranges_are_rejected)
{
	resetIoResourceManagerForTest();
	const IoResourceId invalid[] = {
		dmaMemoryIoResource(nullptr, 16U),
		dmaMemoryIoResource(&dma_buffer[0], 0U),
		{IoResourceKind::dma_memory, &dma_buffer[0], 1U, 16U},
	};
	for (const auto &resource : invalid)
	{
		IoResourceLease lease{};
		zassert_equal(reserveIoResources({IoOwnerKind::application, 0U}, &resource, 1U,
										 IoAcquirePolicy::exclusive, lease),
					  IoResourceResult::invalid_argument,
					  "잘못된 DMA range가 reserve됐습니다.");
	}
}

ZTEST_SUITE(m23_inventory_contract, nullptr, nullptr, nullptr, nullptr, nullptr);
