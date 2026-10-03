/**
 * @file main.cpp
 * @brief M32-W08 Mesh BLOB·DFU 공개 API target compile 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_Mesh_Update.h>

using namespace nucode::mesh;

/** @brief 공개 구조와 API signature를 target compiler로 확인합니다. */
int main()
{
    const BlobTarget targets[] = {{0x0002U}, {0x0003U}};
    BlobTransfer transfer{};
    transfer.id = 0x4E553534424C4F42ULL;
    transfer.size = 4096U;
    transfer.targets = targets;
    transfer.target_count = sizeof(targets) / sizeof(targets[0]);
    transfer.mode = BlobTransferMode::pull;
    std::uint8_t digest[32]{};

    volatile bool execute_contract = false;
    if (execute_contract)
    {
        static_cast<void>(NUCODEMeshUpdate.begin());
        static_cast<void>(NUCODEMeshUpdate.prepareBlobReceive(transfer.id));
        static_cast<void>(NUCODEMeshUpdate.sendBlob(transfer));
        static_cast<void>(NUCODEMeshUpdate.suspendBlob());
        static_cast<void>(NUCODEMeshUpdate.resumeBlob());
        NUCODEMeshUpdate.cancelBlob();
        static_cast<void>(NUCODEMeshUpdate.clientProgress());
        static_cast<void>(NUCODEMeshUpdate.serverProgress());
        static_cast<void>(NUCODEMeshUpdate.expectImageDigest(digest, transfer.size));
        static_cast<void>(NUCODEMeshUpdate.verifyStagedDigest(digest, transfer.size));
        static_cast<void>(NUCODEMeshUpdate.requestTestUpgrade());
        static_cast<void>(NUCODEMeshUpdate.confirmRunningImage());
        NUCODEMeshUpdate.rebootToApply();
        static_cast<void>(NUCODEMeshUpdate.phase());
        static_cast<void>(NUCODEMeshUpdate.distributionPhase());
    }
    return 0;
}
