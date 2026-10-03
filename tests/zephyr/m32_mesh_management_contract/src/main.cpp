/**
 * @file main.cpp
 * @brief M32-W07 Mesh 1.1 관리 API target compile 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_Mesh_Management.h>

using namespace nucode::mesh;

/** @brief 공개 구조와 API signature를 target compiler로 확인합니다. */
int main()
{
    ManagementTarget target{};
    target.address = 0x0002U;
    SarTransmitter transmitter{};
    SarReceiver receiver{};
    LargeDataChunk chunk{};
    BridgeEntry bridge{};
    RemoteDevice remote{};

    std::uint8_t uuid[16]{};
    volatile bool execute_contract = false;
    if (execute_contract)
    {
        static_cast<void>(NUCODEMeshManagement.begin(5000U));
        static_cast<void>(NUCODEMeshManagement.startRemoteScan(target, 1U, 1U, uuid));
        static_cast<void>(NUCODEMeshManagement.stopRemoteScan(target));
        static_cast<void>(NUCODEMeshManagement.closeRemoteLink(target));
        static_cast<void>(NUCODEMeshManagement.provisionRemote(target, uuid));
        static_cast<void>(NUCODEMeshManagement.getSarTransmitter(target, transmitter));
        static_cast<void>(NUCODEMeshManagement.setSarTransmitter(target, transmitter));
        static_cast<void>(NUCODEMeshManagement.getSarReceiver(target, receiver));
        static_cast<void>(NUCODEMeshManagement.setSarReceiver(target, receiver));
        static_cast<void>(NUCODEMeshManagement.beginOpcodeSequence(target, 0U,
                                                                    target.address));
        static_cast<void>(NUCODEMeshManagement.opcodeSequenceTailroom());
        static_cast<void>(NUCODEMeshManagement.sendOpcodeSequence());
        NUCODEMeshManagement.abortOpcodeSequence();
        static_cast<void>(NUCODEMeshManagement.readLargeComposition(target, 0U, 0U,
                                                                     chunk));
        static_cast<void>(NUCODEMeshManagement.readModelsMetadata(target, 0U, 0U,
                                                                   chunk));
        static_cast<void>(NUCODEMeshManagement.setPrivateBeacon(target, true, 1U));
        static_cast<void>(NUCODEMeshManagement.setPrivateGattProxy(target, true));
        static_cast<void>(NUCODEMeshManagement.setPrivateNodeIdentity(target, 0U, true));
        static_cast<void>(NUCODEMeshManagement.setOnDemandPrivateProxy(target, 10U));
        static_cast<void>(NUCODEMeshManagement.solicit(0U));
        static_cast<void>(NUCODEMeshManagement.clearSolicitationReplay(target, 1U, 2U));
        static_cast<void>(NUCODEMeshManagement.setSubnetBridge(target, true));
        static_cast<void>(NUCODEMeshManagement.addBridgeEntry(target, bridge));
        static_cast<void>(NUCODEMeshManagement.removeBridgeEntry(target, bridge));
    }
    (void)remote;
    return 0;
}
