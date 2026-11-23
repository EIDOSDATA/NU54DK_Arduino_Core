/** @file @brief 생성된 Fast Pair input main 안에서 reset 후 광고 재시작을 차단합니다.
 * SPDX-License-Identifier: MIT
 * @note main의 static work·advertising 상태에 접근하므로 generated main 끝에서만 포함합니다.
 */

/** @brief cooperative context에서 모든 광고 재시작 경로를 비활성화합니다. */
int companion_reset_prepare(void)
{
    companion_reset_locked = true;
    (void)k_work_cancel_delayable(&fp_disc_adv_timeout);
    (void)k_work_cancel(&bt_adv_restart);
    (void)k_work_cancel_delayable(&fp_adv_mode_status_led_handle);
    return bt_adv_helper_adv_stop();
}
