"""! @brief 고정 NCS BAP client 복사본에 원격 ASCS 거부 시험 코드를 생성합니다. """

import argparse
import hashlib
import json
from pathlib import Path
import shutil


MAIN_SHA256 = "3dfb726cbd94c960e3c52c712de3b2e40639d35c5753f64c1e5e76d07ca42cfb"
CMAKE_SHA256 = "5643c568de1b3459fe85d307f1362b69b15430f274d06428e72e990f20913331"


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
        "else()\n"
        "  message(FATAL_ERROR \"M31_BAP_NEGATIVE_CASE must be codec or qos\")\n"
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
    main = replace_once(
        main,
        "\tfor (size_t i = 0; i < ARRAY_SIZE(streams); i++) {\n"
        "\t\tstreams[i].ops = &stream_ops;\n"
        "\t}\n",
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
