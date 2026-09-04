/**
 * @file LittleFS.cpp
 * @brief NU54DK 전용 partition의 비파괴 LittleFS mount를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <LittleFS.h>

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)

#include <errno.h>

#include <zephyr/devicetree.h>
#include <zephyr/fs/fs.h>
#include <zephyr/fs/littlefs.h>
#include <zephyr/kernel.h>
#include <zephyr/storage/flash_map.h>

namespace nucode::littlefs::internal
{
	extern k_mutex filesystem_mutex;
	extern bool filesystem_mounted;
	FSError recordError(FSError error, int driver_error) noexcept;
	FSError recordDriverError(int result) noexcept;
	bool isThreadContext() noexcept;
	bool hasOpenFiles() noexcept;
	extern atomic_t last_error_value;
	extern atomic_t last_driver_error_value;
	extern const char mount_point[];
}

namespace
{
	using namespace nucode::littlefs::internal;

	static_assert(DT_NODE_EXISTS(DT_NODELABEL(arduino_fs_partition)),
				  "arduino_fs_partition이 profile overlay에 필요합니다.");
	static_assert(DT_REG_ADDR(DT_NODELABEL(arduino_fs_partition)) == 0x16c000,
				  "LittleFS partition 시작 주소가 AC-03 계약과 다릅니다.");
	static_assert(DT_REG_SIZE(DT_NODELABEL(arduino_fs_partition)) == 0x8000,
				  "LittleFS partition 크기가 AC-03 계약과 다릅니다.");

	FS_LITTLEFS_DECLARE_DEFAULT_CONFIG(arduino_littlefs_configuration);
	fs_mount_t arduino_littlefs_mount{};
	bool mount_initialized = false;

	/** @brief 고정 partition의 mount 구조를 한 번만 초기화합니다. */
	void initializeMount() noexcept
	{
		if (!mount_initialized)
		{
			arduino_littlefs_mount.type = FS_LITTLEFS;
			arduino_littlefs_mount.mnt_point = mount_point;
			arduino_littlefs_mount.fs_data = &arduino_littlefs_configuration;
			arduino_littlefs_mount.storage_dev = reinterpret_cast<void *>(
				static_cast<std::uintptr_t>(
					DT_FIXED_PARTITION_ID(DT_NODELABEL(arduino_fs_partition))));
			arduino_littlefs_mount.flags = FS_MOUNT_FLAG_NO_FORMAT;
			mount_initialized = true;
		}
	}

	/** @brief NO_FORMAT flag를 유지한 채 filesystem을 mount합니다. */
	int mountWithoutFormatting() noexcept
	{
		initializeMount();
		arduino_littlefs_mount.flags = FS_MOUNT_FLAG_NO_FORMAT;
		return fs_mount(&arduino_littlefs_mount);
	}

	/** @brief 호출자가 mutex를 가진 상태에서 LittleFS를 명시적으로 포맷합니다. */
	int formatLocked() noexcept
	{
		initializeMount();
		return fs_mkfs(FS_LITTLEFS,
					   reinterpret_cast<std::uintptr_t>(arduino_littlefs_mount.storage_dev),
					   arduino_littlefs_mount.fs_data, 0);
	}
}

LittleFSClass LittleFS;

bool LittleFSClass::begin(bool format_on_fail)
{
	using namespace nucode::littlefs::internal;
	if (!isThreadContext())
	{
		return false;
	}
	static_cast<void>(k_mutex_lock(&filesystem_mutex, K_FOREVER));
	if (filesystem_mounted)
	{
		recordError(FSError::none, 0);
		static_cast<void>(k_mutex_unlock(&filesystem_mutex));
		return true;
	}
	int result = mountWithoutFormatting();
	if (result < 0 && format_on_fail)
	{
		result = formatLocked();
		if (result == 0)
		{
			result = mountWithoutFormatting();
		}
	}
	filesystem_mounted = result == 0;
	if (result < 0)
	{
		recordDriverError(result);
	}
	else
	{
		recordError(FSError::none, 0);
	}
	static_cast<void>(k_mutex_unlock(&filesystem_mutex));
	return result == 0;
}

bool LittleFSClass::end()
{
	using namespace nucode::littlefs::internal;
	if (!isThreadContext())
	{
		return false;
	}
	static_cast<void>(k_mutex_lock(&filesystem_mutex, K_FOREVER));
	if (!filesystem_mounted)
	{
		recordError(FSError::none, 0);
		static_cast<void>(k_mutex_unlock(&filesystem_mutex));
		return true;
	}
	if (hasOpenFiles())
	{
		recordError(FSError::busy, -EBUSY);
		static_cast<void>(k_mutex_unlock(&filesystem_mutex));
		return false;
	}
	const int result = fs_unmount(&arduino_littlefs_mount);
	if (result == 0)
	{
		filesystem_mounted = false;
		recordError(FSError::none, 0);
	}
	else
	{
		recordDriverError(result);
	}
	static_cast<void>(k_mutex_unlock(&filesystem_mutex));
	return result == 0;
}

bool LittleFSClass::format()
{
	using namespace nucode::littlefs::internal;
	if (!isThreadContext())
	{
		return false;
	}
	static_cast<void>(k_mutex_lock(&filesystem_mutex, K_FOREVER));
	if (hasOpenFiles())
	{
		recordError(FSError::busy, -EBUSY);
		static_cast<void>(k_mutex_unlock(&filesystem_mutex));
		return false;
	}
	int result = 0;
	if (filesystem_mounted)
	{
		result = fs_unmount(&arduino_littlefs_mount);
		if (result == 0)
		{
			filesystem_mounted = false;
		}
	}
	if (result == 0)
	{
		result = formatLocked();
	}
	if (result == 0)
	{
		result = mountWithoutFormatting();
	}
	filesystem_mounted = result == 0;
	if (result < 0)
	{
		recordDriverError(result);
	}
	else
	{
		recordError(FSError::none, 0);
	}
	static_cast<void>(k_mutex_unlock(&filesystem_mutex));
	return result == 0;
}

std::size_t LittleFSClass::totalBytes()
{
	using namespace nucode::littlefs::internal;
	if (!isThreadContext())
	{
		return 0U;
	}
	static_cast<void>(k_mutex_lock(&filesystem_mutex, K_FOREVER));
	struct fs_statvfs information{};
	const int result = filesystem_mounted ? fs_statvfs(mount_point, &information) : -ENODEV;
	if (result < 0)
	{
		result == -ENODEV ? recordError(FSError::not_mounted, result) : recordDriverError(result);
	}
	else
	{
		recordError(FSError::none, 0);
	}
	static_cast<void>(k_mutex_unlock(&filesystem_mutex));
	return result < 0 ? 0U : static_cast<std::size_t>(information.f_frsize) * information.f_blocks;
}

std::size_t LittleFSClass::usedBytes()
{
	using namespace nucode::littlefs::internal;
	if (!isThreadContext())
	{
		return 0U;
	}
	static_cast<void>(k_mutex_lock(&filesystem_mutex, K_FOREVER));
	struct fs_statvfs information{};
	const int result = filesystem_mounted ? fs_statvfs(mount_point, &information) : -ENODEV;
	if (result < 0)
	{
		result == -ENODEV ? recordError(FSError::not_mounted, result) : recordDriverError(result);
	}
	else
	{
		recordError(FSError::none, 0);
	}
	static_cast<void>(k_mutex_unlock(&filesystem_mutex));
	return result < 0 ? 0U : static_cast<std::size_t>(information.f_frsize) * (information.f_blocks - information.f_bfree);
}

bool LittleFSClass::mounted() const noexcept
{
	return nucode::littlefs::internal::filesystem_mounted;
}

FSError LittleFSClass::lastError() const noexcept
{
	return static_cast<FSError>(atomic_get(&nucode::littlefs::internal::last_error_value));
}

int LittleFSClass::lastDriverError() const noexcept
{
	return static_cast<int>(atomic_get(&nucode::littlefs::internal::last_driver_error_value));
}

#endif
