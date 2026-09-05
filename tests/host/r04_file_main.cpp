/** @file @brief production File의 공유 참조·마지막 close·thread 교차를 검증합니다. */
#include "../../libraries/LittleFS/src/FS.cpp"
#include <condition_variable>
#include <iostream>
#include <thread>
using namespace nucode::littlefs::internal;
int main(int argc, char **argv)
{
    assert(argc == 2);
    filesystem_mounted = true;
    FS filesystem;
    File source = filesystem.open("/data", "w+");
    assert(source);
    if (std::strcmp(argv[1], "value") == 0)
    {
        const std::uint8_t bytes[]{1, 2, 3, 4};
        assert(source.write(bytes, sizeof(bytes)) == sizeof(bytes));
        File copy(source), assigned;
        assigned = copy;
        assigned = assigned;
        assigned = copy;
        assert(file_slots[0].references == 3);
        File moved(std::move(copy));
        assert(!copy && moved);
        File destination = filesystem.open("/other", "w+");
        destination = std::move(moved);
        File *const self = &destination;
        destination = std::move(*self);
        assert(!moved && mock_closes == 1 && file_slots[0].references == 3);
        source.close();
        assigned.close();
        assert(destination.seek(0));
        std::uint8_t received[4]{};
        assert(destination.read(received, 4) == 4);
        assert(std::memcmp(received, bytes, 4) == 0);
        destination.close();
        destination.close();
        assert(mock_closes == 2 && !hasOpenFiles());
    }
    else if (std::strcmp(argv[1], "mutex") == 0)
    {
        std::mutex mutex;
        std::condition_variable condition;
        bool attempting = false, copied = false, finish = false;
        filesystem_mutex.lock();
        std::thread worker(
            [&]
            {
                mock_before_lock = [&]
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    attempting = true;
                    condition.notify_all();
                };
                File copy(source);
                {
                    std::unique_lock<std::mutex> lock(mutex);
                    copied = true;
                    condition.notify_all();
                    condition.wait(lock,
                                   [&]
                                   {
                                       return finish;
                                   });
                }
            });
        bool locked;
        {
            std::unique_lock<std::mutex> lock(mutex);
            condition.wait(lock,
                           [&]
                           {
                               return attempting || copied;
                           });
            locked = attempting && !copied;
            finish = true;
            condition.notify_all();
        }
        filesystem_mutex.unlock();
        worker.join();
        assert(locked);
        assert(file_slots[0].references == 1 && mock_closes == 0);
    }
    else if (std::strcmp(argv[1], "threads") == 0)
    {
        std::vector<std::thread> workers;
        for (unsigned t = 0; t < 8; ++t)
        {
            workers.emplace_back(
                [&]
                {
                    for (unsigned i = 0; i < 4000; ++i)
                    {
                        File copy(source), destination;
                        destination = copy;
                        File moved(std::move(destination));
                        copy.close();
                        assert(moved && std::strcmp(moved.name(), "/data") == 0);
                    }
                });
        }
        for (auto &worker : workers)
        {
            worker.join();
        }
        assert(file_slots[0].references == 1 && mock_closes == 0);
        source.close();
        assert(mock_closes == 1 && !hasOpenFiles());
    }
    else if (std::strcmp(argv[1], "stale") == 0)
    {
        const auto old = file_slots[0].generation;
        File alias(source);
        /** @brief 외부 폐기 후 남은 handle의 오래된 generation을 주입합니다. */
        fs_close(&file_slots[0].file);
        file_slots[0].active = false;
        file_slots[0].references = 0;
        auto replacement = filesystem.open("/replacement", "w+");
        assert(file_slots[0].generation != old);
        File stale(source);
        assert(!stale);
        source.close();
        alias.close();
        assert(mock_closes == 1 && file_slots[0].references == 1 && replacement);
        replacement.close();
        file_slots[0].generation = UINT32_MAX;
        auto wrapped = filesystem.open("/wrapped", "w+");
        assert(file_slots[0].generation == 1 && wrapped);
        wrapped.close();
        assert(mock_closes == 3);
    }
    else if (std::strcmp(argv[1], "saturation") == 0)
    {
        file_slots[0].references = UINT16_MAX;
        File copy(source);
        assert(!copy && file_slots[0].references == UINT16_MAX);
        file_slots[0].references = 1;
        File invalid;
        source = invalid;
        assert(!source && mock_closes == 1);
    }
    else if (std::strcmp(argv[1], "close_error") == 0)
    {
        mock_close_error = -EIO;
        source.close();
        assert(!source && mock_closes == 1 && !hasOpenFiles());
        assert(atomic_get(&last_error_value) == static_cast<int>(FSError::driver_error));
        assert(atomic_get(&last_driver_error_value) == -EIO);
    }
    else if (std::strcmp(argv[1], "isr") == 0)
    {
        File destination = filesystem.open("/destination", "w+");
        mock_in_isr = true;
        File copy(source);
        destination = source;
        File moved(std::move(source));
        destination = std::move(source);
        mock_in_isr = false;
        assert(!copy && !moved && source && file_slots[0].references == 1 &&
               file_slots[1].references == 1);
        assert(std::strcmp(destination.name(), "/destination") == 0);
        destination.close();
    }
    else if (std::strcmp(argv[1], "last_threads") == 0)
    {
        File first(source), last(source);
        source.close();
        std::atomic<bool> go{false};
        std::thread one(
            [&]
            {
                while (!go)
                {
                    std::this_thread::yield();
                }
                first.close();
            });
        std::thread two(
            [&]
            {
                while (!go)
                {
                    std::this_thread::yield();
                }
                last.close();
            });
        go = true;
        one.join();
        two.join();
        assert(mock_closes == 1 && !hasOpenFiles());
    }
    else
    {
        return 2;
    }
    source.close();
    std::cout << "R04_FILE_PASS=" << argv[1] << '\n';
}
