/**
 * @file FS.h
 * @brief NU54DK의 고정 메모리 Arduino 파일 API를 정의합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_LIBRARY_FS_H_
#define NUCODE_ARDUINO_LIBRARY_FS_H_

#include <Stream.h>

#include <cstddef>
#include <cstdint>

/** @brief 파일을 읽기 전용으로 여는 Arduino 호환 mode입니다. */
#define FILE_READ "r"
/** @brief 파일을 만들거나 비우고 쓰는 Arduino 호환 mode입니다. */
#define FILE_WRITE "w"
/** @brief 파일 끝에 추가하는 Arduino 호환 mode입니다. */
#define FILE_APPEND "a"

class FS;

/** @brief 파일 시스템 API의 안정된 오류 분류입니다. */
enum class FSError : std::uint8_t
{
	none = 0U,
	invalid_argument,
	invalid_context,
	not_mounted,
	not_found,
	already_exists,
	busy,
	no_space,
	corrupt,
	driver_error,
};

/** @brief Zephyr file handle을 Arduino Stream으로 노출하는 이동 전용 객체입니다. */
class File final : public Stream
{
public:
	/** @brief 닫힌 파일 객체를 만듭니다. */
	File() noexcept;

	/** @brief 같은 고정 handle의 참조를 하나 추가합니다. */
	File(const File &other) noexcept;

	/** @brief 기존 참조를 닫고 같은 고정 handle의 참조를 하나 추가합니다. */
	File &operator=(const File &other) noexcept;

	/** @brief 열려 있는 handle의 소유권을 이동합니다. */
	File(File &&other) noexcept;

	/** @brief 기존 handle을 닫고 다른 handle의 소유권을 이동합니다. */
	File &operator=(File &&other) noexcept;

	/** @brief 열린 handle을 닫습니다. */
	~File();

	using Print::write;

	/** @brief 파일 끝까지 남은 byte 수를 반환합니다. */
	int available() override;

	/** @brief 다음 byte를 읽거나 EOF에서 -1을 반환합니다. */
	int read() override;

	/** @brief byte 묶음을 읽고 실제 읽은 길이를 반환합니다. */
	int read(std::uint8_t *buffer, std::size_t size);

	/** @brief 다음 byte를 소비하지 않고 읽거나 EOF에서 -1을 반환합니다. */
	int peek() override;

	/** @brief 한 byte를 파일에 씁니다. */
	std::size_t write(std::uint8_t value) override;

	/** @brief byte 묶음을 파일에 씁니다. */
	std::size_t write(const std::uint8_t *buffer, std::size_t size) override;

	/** @brief 현재 위치를 파일 시작 기준으로 옮깁니다. */
	bool seek(std::uint32_t position);

	/** @brief 현재 파일 위치를 반환합니다. */
	std::size_t position() const;

	/** @brief 현재 파일 크기를 반환합니다. */
	std::size_t size() const;

	/** @brief backend buffer를 저장 장치에 동기화합니다. */
	void flush() override;

	/** @brief 파일 handle을 명시적으로 닫습니다. */
	void close();

	/** @brief 파일을 열 때 사용한 mount 상대 경로를 반환합니다. */
	const char *name() const noexcept;

	/** @brief handle이 아직 유효한지 반환합니다. */
	explicit operator bool() const noexcept;

private:
	friend class FS;

	/** @brief 내부 slot과 세대를 소유하는 열린 파일을 만듭니다. */
	File(std::uint8_t slot, std::uint32_t generation) noexcept;

	std::uint8_t slot_;
	std::uint32_t generation_;
};

/** @brief mount된 LittleFS에 Arduino 경로 작업을 제공하는 facade입니다. */
class FS
{
public:
	/** @brief 파일을 지정 mode로 엽니다. */
	File open(const char *path, const char *mode = FILE_READ);

	/** @brief Arduino String 경로의 파일을 지정 mode로 엽니다. */
	File open(const String &path, const char *mode = FILE_READ)
	{
		return open(path.c_str(), mode);
	}

	/** @brief 파일 또는 directory가 존재하는지 반환합니다. */
	bool exists(const char *path);

	/** @brief Arduino String 경로가 존재하는지 반환합니다. */
	bool exists(const String &path) { return exists(path.c_str()); }

	/** @brief 파일을 제거합니다. */
	bool remove(const char *path);

	/** @brief Arduino String 경로의 파일을 제거합니다. */
	bool remove(const String &path) { return remove(path.c_str()); }

	/** @brief 파일 또는 directory의 이름을 바꿉니다. */
	bool rename(const char *from, const char *to);

	/** @brief 두 Arduino String 경로 사이에서 이름을 바꿉니다. */
	bool rename(const String &from, const String &to)
	{
		return rename(from.c_str(), to.c_str());
	}

	/** @brief directory를 만듭니다. */
	bool mkdir(const char *path);

	/** @brief Arduino String 경로의 directory를 만듭니다. */
	bool mkdir(const String &path) { return mkdir(path.c_str()); }

	/** @brief 비어 있는 directory를 제거합니다. */
	bool rmdir(const char *path);

	/** @brief Arduino String 경로의 빈 directory를 제거합니다. */
	bool rmdir(const String &path) { return rmdir(path.c_str()); }
};

/** @brief ESP 계열 라이브러리가 사용하는 fs namespace 호환 별칭입니다. */
namespace fs
{
	using ::FS;
	using ::File;
}

#endif
