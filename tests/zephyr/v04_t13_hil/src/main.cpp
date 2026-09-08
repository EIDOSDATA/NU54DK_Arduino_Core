/** @file @brief S/U 전용 identity와 nonce/sequence 검사를 갖춘 T13 mailbox입니다. */
#include "engine.h"
#include "protocol.h"
#include <zephyr/kernel.h>
#if defined(CONFIG_NUCODE_T13_POWER)
#include "power.h"
#endif

extern "C"
{
    alignas(4) volatile std::uint32_t v04_request[v04::words]{};
    alignas(4) volatile std::uint32_t v04_response[v04::words]{};
    alignas(4) volatile std::uint32_t v04_identity[16]{};
}

namespace
{
    constexpr std::uint32_t role = CONFIG_NUCODE_V04_HIL_ROLE;
    constexpr char revision[] = NUCODE_HIL_CORE_REVISION;
    static_assert(sizeof(revision) == 41U);
} // namespace

int main()
{
    t13::initializeWiring();
    v04_identity[3] = 0x54313300U | CONFIG_NUCODE_T13_HARNESS;
    v04_identity[1] = v04::version;
    v04_identity[2] = role;
    for (unsigned index = 0; index < 10; ++index)
    {
        std::uint32_t word = 0;
        for (unsigned byte = 0; byte < 4; ++byte)
        {
            word |= static_cast<std::uint32_t>(revision[index * 4 + byte]) << (byte * 8);
        }
        v04_identity[4 + index] = word;
    }
    __DMB();
    v04_identity[0] = v04::magic;
    std::uint32_t last_sequence = 0;
    std::uint32_t session_nonce[4]{};
#if defined(CONFIG_NUCODE_T13_POWER)
    v04_identity[14] = 0x504F5731U;
    t13::power::initialize(last_sequence, session_nonce);
#endif
    while (true)
    {
        t13::wiringService();
        t13::service();
#if defined(CONFIG_NUCODE_T13_POWER)
        std::uint32_t request[v04::words]{}, response[v04::words]{};
        bool from_peer = false;
        t13::power::service();
        from_peer = t13::power::takeRequest(request);
        if (!from_peer && v04_request[0] != v04::magic)
#else
        if (v04_request[0] != v04::magic)
#endif
        {
            if (t13::running())
            {
                k_busy_wait(10U);
            }
            else
            {
                k_sleep(K_MSEC(1));
            }
            continue;
        }
        __DMB();
#if !defined(CONFIG_NUCODE_T13_POWER)
        std::uint32_t request[v04::words]{}, response[v04::words]{};
        constexpr bool from_peer = false;
#endif
        if (!from_peer)
        {
            for (unsigned index = 0; index < v04::words; ++index)
            {
                request[index] = v04_request[index];
            }
            v04_request[0] = 0;
        }
        for (unsigned index = 0; index < 9; ++index)
        {
            response[index] = request[index];
        }
        bool same_nonce = true;
        for (unsigned index = 0; index < 4; ++index)
        {
            same_nonce &= request[5 + index] == session_nonce[index];
        }
        if (!v04::valid(request, role) || request[2] != last_sequence + 1 ||
            (last_sequence != 0 && !same_nonce))
        {
            response[9] = 409;
        }
        else
        {
            for (unsigned index = 0; index < 4; ++index)
            {
                session_nonce[index] = request[5 + index];
            }
            last_sequence = request[2];
#if defined(CONFIG_NUCODE_T13_POWER)
            if (request[4] >= 130U && request[4] <= 139U)
            {
                response[9] = t13::power::command(request[4], request + 11, request[10],
                                                  response + 11, response[10], from_peer);
            }
            else if (t13::power::claimed())
            {
                response[9] = 403U;
            }
            else
#endif
            {
                response[9] = t13::command(request[4], request + 11, request[10], response + 11,
                                           response[10]);
            }
#if defined(CONFIG_NUCODE_T13_POWER)
            t13::power::remember(last_sequence, session_nonce);
#endif
        }
        response[31] = v04::checksum(response);
#if defined(CONFIG_NUCODE_T13_POWER)
        if (from_peer)
        {
            static_cast<void>(t13::power::respond(response));
            continue;
        }
#endif
        v04_response[0] = 0;
        for (unsigned index = 1; index < v04::words; ++index)
        {
            v04_response[index] = response[index];
        }
        __DMB();
        v04_response[0] = v04::magic;
    }
}
