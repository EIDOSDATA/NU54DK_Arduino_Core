/** @file @brief C bridge 호출을 C++ Host 오류 주입 상태로 연결합니다. */
#include <security_mock.h>
int bt_hids_init(bt_hids *, bt_hids_init_param *p)
{
    mock_hids_parameters = *p;
    return mock_hids_init_error;
}
int bt_hids_connected(bt_hids *, bt_conn *)
{
    ++mock_hids_attach_calls;
    return mock_hids_attach_error;
}
int bt_hids_disconnected(bt_hids *, bt_conn *)
{
    ++mock_hids_detach_calls;
    return mock_hids_detach_error;
}
int bt_hids_boot_kb_inp_rep_send(bt_hids *, bt_conn *, const std::uint8_t *data, std::size_t size,
                                 void *)
{
    assert(size == 8);
    ++mock_hids_send_calls;
    mock_hids_boot = true;
    mock_hids_report_index = 0;
    mock_hids_report_size = size;
    std::memcpy(mock_hids_data, data, size);
    return mock_hids_send_error;
}
int bt_hids_inp_rep_send(bt_hids *, bt_conn *, std::uint8_t index, const std::uint8_t *data,
                         std::size_t size, void *)
{
    assert(index < 3 && size <= sizeof(mock_hids_data));
    ++mock_hids_send_calls;
    mock_hids_boot = false;
    mock_hids_report_index = index;
    mock_hids_report_size = size;
    std::memcpy(mock_hids_data, data, size);
    return mock_hids_send_error;
}
