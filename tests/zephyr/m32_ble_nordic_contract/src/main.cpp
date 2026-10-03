/** @file @brief M32-W05 Nordic extension 공개 API의 target link 계약을 검사합니다. */
#include <NUCODE_BLE_GAP.h>

using namespace nucode::ble;

/** @brief callback signature를 target compiler에 고정합니다. */
void onConnectionEvent(const BLENordicConnectionEventReport &, void *)
{
}

/** @brief callback signature를 target compiler에 고정합니다. */
void onChannelSurvey(const BLENordicChannelSurveyReport &, void *)
{
}

/** @brief callback signature를 target compiler에 고정합니다. */
void onAnchorPoint(const BLENordicAnchorPointReport &, void *)
{
}

/** @brief Nordic profile의 모든 공개 entry point를 link합니다. */
int main()
{
    BLENordic.onConnectionEvent(onConnectionEvent);
    BLENordic.onChannelSurvey(onChannelSurvey);
    BLENordic.onAnchorPoint(onAnchorPoint);

    BLENordicAnchorPointReport anchor;
    std::uint64_t projected = 0U;
    static_cast<void>(BLENordic.projectAnchorPoint(anchor, 1U, 7500U, projected));
    static_cast<void>(BLENordic.availableConnectionEventReports());
    static_cast<void>(BLENordic.availableChannelSurveyReports());
    static_cast<void>(BLENordic.availableAnchorPointReports());
    static_cast<void>(BLENordic.droppedReports());
    static_cast<void>(BLENordic.flushableAclSupport());
    return 0;
}
