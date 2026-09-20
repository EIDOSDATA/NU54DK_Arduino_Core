"""! @brief 고정 NCS BAP client 복사본에 원격 ASCS 거부 시험 코드를 생성합니다. """

import argparse
import hashlib
import json
from pathlib import Path
import shutil


MAIN_SHA256 = "3dfb726cbd94c960e3c52c712de3b2e40639d35c5753f64c1e5e76d07ca42cfb"
CMAKE_SHA256 = "5643c568de1b3459fe85d307f1362b69b15430f274d06428e72e990f20913331"

STATE_CLIENT_CODE = '''#if defined(M31_BAP_NEG_STATE)
static K_SEM_DEFINE(sem_negative_cp, 0, 1);
static K_SEM_DEFINE(sem_negative_rsp, 0, 1);
static uint16_t negative_cp_handle;
static uint8_t negative_ase_id;
static struct bt_gatt_discover_params negative_discover;
static struct bt_gatt_subscribe_params negative_subscribe;

/** @brief 고정 서버의 ASCS 제어 지점을 UUID로 찾습니다. */
static uint8_t negative_cp_discovered(struct bt_conn *conn,
                                      const struct bt_gatt_attr *attr,
                                      struct bt_gatt_discover_params *params)
{
    ARG_UNUSED(conn);
    ARG_UNUSED(params);
    if (attr != NULL)
    {
        const struct bt_gatt_chrc *chrc = attr->user_data;
        negative_cp_handle = chrc->value_handle;
    }
    k_sem_give(&sem_negative_cp);
    return BT_GATT_ITER_STOP;
}

/** @brief idle ASE에 대한 release 거부 응답을 원격 알림에서 확인합니다. */
static uint8_t negative_state_notified(struct bt_conn *conn,
                                       struct bt_gatt_subscribe_params *params,
                                       const void *data, uint16_t length)
{
    ARG_UNUSED(conn);
    ARG_UNUSED(params);
    if (data != NULL && length >= 5U)
    {
        const uint8_t *response = data;
        if (response[0] == 0x08U && response[1] == 1U &&
            response[2] == negative_ase_id)
        {
            printk("M31_NEG_STATE_RSP code=%u reason=%u\\n",
                   response[3], response[4]);
            k_sem_give(&sem_negative_rsp);
        }
    }
    return BT_GATT_ITER_CONTINUE;
}

/** @brief 아직 idle인 원격 ASE에 release 요청을 전송합니다. */
static int negative_state_request(void)
{
    struct bt_bap_ep_info ep_info;
    uint8_t request[3];
    int err;

    if (sinks[0].ep == NULL)
    {
        return -ENOENT;
    }
    err = bt_bap_ep_get_info(sinks[0].ep, &ep_info);
    if (err != 0 || ep_info.state != BT_BAP_EP_STATE_IDLE)
    {
        return -EINVAL;
    }
    negative_ase_id = ep_info.id;
    negative_discover.uuid = BT_UUID_ASCS_ASE_CP;
    negative_discover.func = negative_cp_discovered;
    negative_discover.start_handle = BT_ATT_FIRST_ATTRIBUTE_HANDLE;
    negative_discover.end_handle = BT_ATT_LAST_ATTRIBUTE_HANDLE;
    negative_discover.type = BT_GATT_DISCOVER_CHARACTERISTIC;
    err = bt_gatt_discover(default_conn, &negative_discover);
    if (err != 0 || k_sem_take(&sem_negative_cp, K_SECONDS(5)) != 0 ||
        negative_cp_handle == 0U)
    {
        return -EIO;
    }

    negative_subscribe.notify = negative_state_notified;
    negative_subscribe.value_handle = negative_cp_handle;
    negative_subscribe.ccc_handle = negative_cp_handle + 1U;
    negative_subscribe.value = BT_GATT_CCC_NOTIFY;
    err = bt_gatt_subscribe(default_conn, &negative_subscribe);
    if (err != 0)
    {
        return err;
    }
    request[0] = 0x08U;
    request[1] = 1U;
    request[2] = negative_ase_id;
    err = bt_gatt_write_without_response(default_conn, negative_cp_handle,
                                         request, sizeof(request), false);
    if (err != 0 || k_sem_take(&sem_negative_rsp, K_SECONDS(5)) != 0)
    {
        return -EIO;
    }
    return 0;
}
#endif

'''


def sha256(path: Path) -> str:
    """! @brief 고정 upstream 파일의 byte 해시를 계산합니다. """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text: str, before: str, after: str) -> str:
    """! @brief 고정 SDK anchor가 정확히 하나일 때만 교체합니다. """
    if text.count(before) != 1:
        raise RuntimeError(f"upstream anchor drift: {before[:60]!r}")
    return text.replace(before, after)


def prepare(source: Path, destination: Path) -> dict[str, str]:
    """! @brief upstream sample을 수정 없이 보존하고 외부 복사본만 패치합니다. """
    main_file = source / "src/main.c"
    cmake_file = source / "CMakeLists.txt"
    if (sha256(main_file) != MAIN_SHA256 or sha256(cmake_file) != CMAKE_SHA256):
        raise RuntimeError("fixed NCS BAP client source hash mismatch")
    if destination.exists():
        raise FileExistsError(destination)

    main = main_file.read_text(encoding="utf-8")
    cmake = cmake_file.read_text(encoding="utf-8")
    cmake = replace_once(
        cmake,
        "project(bap_unicast_client)\n",
        "project(bap_unicast_client)\n\n"
        "if(M31_BAP_NEGATIVE_CASE STREQUAL \"codec\")\n"
        "  target_compile_definitions(app PRIVATE M31_BAP_NEG_CODEC=1)\n"
        "elseif(M31_BAP_NEGATIVE_CASE STREQUAL \"qos\")\n"
        "  target_compile_definitions(app PRIVATE M31_BAP_NEG_QOS=1)\n"
        "elseif(M31_BAP_NEGATIVE_CASE STREQUAL \"state\")\n"
        "  target_compile_definitions(app PRIVATE M31_BAP_NEG_STATE=1)\n"
        "else()\n"
        "  message(FATAL_ERROR \"M31_BAP_NEGATIVE_CASE must be codec, qos or state\")\n"
        "endif()\n",
    )
    main = replace_once(
        main,
        "static struct bt_bap_unicast_client_cb unicast_client_cbs = {\n",
        "/** @brief 원격 codec 설정 거부 응답을 기록합니다. */\n"
        "static void negative_config_rsp(struct bt_bap_stream *stream,\n"
        "                                enum bt_bap_ascs_rsp_code code,\n"
        "                                enum bt_bap_ascs_reason reason)\n"
        "{\n"
        "    ARG_UNUSED(stream);\n"
        "#if defined(M31_BAP_NEG_CODEC)\n"
        "    printk(\"M31_NEG_CODEC_RSP code=%u reason=%u\\n\", code, reason);\n"
        "#endif\n"
        "}\n\n"
        "/** @brief 원격 QoS 설정 거부 응답을 기록합니다. */\n"
        "static void negative_qos_rsp(struct bt_bap_stream *stream,\n"
        "                             enum bt_bap_ascs_rsp_code code,\n"
        "                             enum bt_bap_ascs_reason reason)\n"
        "{\n"
        "    ARG_UNUSED(stream);\n"
        "#if defined(M31_BAP_NEG_QOS)\n"
        "    printk(\"M31_NEG_QOS_RSP code=%u reason=%u\\n\", code, reason);\n"
        "#endif\n"
        "}\n\n"
        "static struct bt_bap_unicast_client_cb unicast_client_cbs = {\n",
    )
    main = replace_once(
        main,
        "\t.endpoint = endpoint_cb,\n};\n",
        "\t.endpoint = endpoint_cb,\n"
        "\t.config = negative_config_rsp,\n"
        "\t.qos = negative_qos_rsp,\n"
        "};\n",
    )
    main = replace_once(main, "int main(void)\n{\n", STATE_CLIENT_CODE + "int main(void)\n{\n")
    main = replace_once(
        main,
        "\tfor (size_t i = 0; i < ARRAY_SIZE(streams); i++) {\n"
        "\t\tstreams[i].ops = &stream_ops;\n"
        "\t}\n",
        "    /** @brief 반복 재시작에서 휘발성 bond 불일치를 남기지 않습니다. */\n"
        "    bt_set_bondable(false);\n\n"
        "#if defined(M31_BAP_NEG_CODEC)\n"
        "    /** @brief 서버가 광고하지 않은 24 kHz LC3를 요청합니다. */\n"
        "    err = bt_audio_codec_cfg_set_freq(&codec_configuration.codec_cfg,\n"
        "                                      BT_AUDIO_CODEC_CFG_FREQ_24KHZ);\n"
        "    if (err < 0)\n"
        "    {\n"
        "        printk(\"M31_NEG_LOCAL_CODEC_ERROR=%d\\n\", err);\n"
        "        return err;\n"
        "    }\n"
        "#elif defined(M31_BAP_NEG_QOS)\n"
        "    /** @brief 서버의 고정 40 byte SDU보다 큰 41 byte를 요청합니다. */\n"
        "    codec_configuration.qos.sdu = 41U;\n"
        "#endif\n\n"
        "\tfor (size_t i = 0; i < ARRAY_SIZE(streams); i++) {\n"
        "\t\tstreams[i].ops = &stream_ops;\n"
        "\t}\n",
    )
    main = replace_once(
        main,
        "\t\tprintk(\"Sinks discovered\\n\");\n",
        "\t\tprintk(\"Sinks discovered\\n\");\n"
        "#if defined(M31_BAP_NEG_STATE)\n"
        "        err = negative_state_request();\n"
        "        if (err != 0)\n"
        "        {\n"
        "            printk(\"M31_NEG_STATE_LOCAL_ERROR=%d\\n\", err);\n"
        "        }\n"
        "        return 0;\n"
        "#endif\n",
    )

    shutil.copytree(source, destination)
    (destination / "src/main.c").write_text(main, encoding="utf-8", newline="\n")
    (destination / "CMakeLists.txt").write_text(cmake, encoding="utf-8", newline="\n")
    return {
        "upstream_main_sha256": MAIN_SHA256,
        "upstream_cmake_sha256": CMAKE_SHA256,
        "generated_main_sha256": sha256(destination / "src/main.c"),
        "generated_cmake_sha256": sha256(destination / "CMakeLists.txt"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--record", required=True, type=Path)
    arguments = parser.parse_args()
    record = prepare(arguments.source, arguments.destination)
    arguments.record.parent.mkdir(parents=True, exist_ok=True)
    arguments.record.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print("M31_BAP_NEGATIVE_FIXTURE_PREPARED")


if __name__ == "__main__":
    main()
