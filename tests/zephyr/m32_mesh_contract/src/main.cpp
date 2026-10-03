/** @file @brief M32-W06 Mesh 공개 API의 target link 계약을 검사합니다. */

#include <NUCODE_BLE_Mesh.h>

using namespace nucode::mesh;

/** @brief 공개 callback signature를 target compiler에 고정합니다. */
void onMeshEvent(const EventRecord &, void *)
{
}

/** @brief provisioning, 역할과 모든 표준 model entry point를 link합니다. */
int main()
{
    Configuration configuration{};
    configuration.role = Role::node;
    configuration.bearers = Bearer::all;
    Destination destination{};
    destination.force_segment_acknowledgment = true;
    const std::uint8_t app_key[16]{};
    HealthFaults faults{};
    Publication publication{};

    NUCODEMesh.onEvent(onMeshEvent);
    static_cast<void>(NUCODEMesh.provisioned());
    static_cast<void>(NUCODEMesh.configureAppKey(0x0002U, app_key));
    static_cast<void>(NUCODEMesh.updateKeys(0x0002U, app_key, app_key));
    static_cast<void>(NUCODEMesh.transitionKeyRefresh(
        0x0002U, KeyRefreshTransition::use_new_keys));
    static_cast<void>(NUCODEMesh.bindModel(0x0002U, 0x0002U, Model::generic_on_off));
    static_cast<void>(NUCODEMesh.subscribeModel(0x0002U, 0x0002U,
                                                Model::generic_on_off, 0xC000U));
    static_cast<void>(NUCODEMesh.configurePublication(0x0002U, 0x0002U,
                                                      Model::generic_on_off,
                                                      publication));
    static_cast<void>(NUCODEMesh.readHealthFaults(destination, 0x0054U, faults));
    static_cast<void>(NUCODEMesh.sendOnOff(destination, true, true));
    static_cast<void>(NUCODEMesh.setLocalOnOff(true, false));
    static_cast<void>(NUCODEMesh.localOnOff());
    static_cast<void>(NUCODEMesh.sendLevel(destination, 0, false));
    static_cast<void>(NUCODEMesh.sendLightness(destination, 0x8000U, true));
    static_cast<void>(NUCODEMesh.requestSensor(destination));
    static_cast<void>(NUCODEMesh.requestTime(destination));
    static_cast<void>(NUCODEMesh.recallScene(destination, 1U, true));
    static_cast<void>(NUCODEMesh.requestSchedule(destination));
    static_cast<void>(NUCODEMesh.droppedEvents());
    static_cast<void>(NUCODEMesh.lastError());
    static_cast<void>(NUCODEMesh.lastDriverError());
    static_cast<void>(NUCODEMesh.lastConfigurationStatus());
    return 0;
}
