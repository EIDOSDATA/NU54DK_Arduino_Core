"""! @brief 고정 NCS CAP Acceptor에 원격 Enable 거부 시험 코드를 생성합니다. """

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


NCS_REVISION = "99553055607b2e9885fbc80ccd11fa9da81c2df0"
ZEPHYR_REVISION = "bf801e4e3d19e1ffa76164346480cb7734dd2800"
SOURCE_HASHES = {
    "CMakeLists.txt": "f2d60560b08ee0ed26cd8b721852b6424ab3357ce9af02f43e029f6ab93df165",
    "prj.conf": "8916dbd7f222c49155e8a070c78c86bcefadad77ab5d64a9a2a4a91092cbe5f5",
    "src/cap_acceptor.h":
        "316cf4a55329f554878be958525bf616df2a1ac3caa13b28fb1a4e6ca8e68251",
    "src/cap_acceptor_unicast.c":
        "26f6a42543d203879c671b0037edd1a86e07638882ceb2634f9bae4a8d146356",
    "src/main.c": "da698ad281a56ad4cebb25735abaadf70c114429cead3338de98977de626c1f6",
}


def sha256(path: Path) -> str:
    """! @brief 파일 byte의 SHA-256을 반환합니다. """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def revision(repository: Path) -> str:
    """! @brief 저장소의 정확한 HEAD revision을 조회합니다. """
    result = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def replace_once(text: str, before: str, after: str) -> str:
    """! @brief 고정 upstream anchor가 정확히 하나일 때만 교체합니다. """
    if text.count(before) != 1:
        raise RuntimeError(f"upstream anchor drift: {before[:72]!r}")
    return text.replace(before, after)


def verify_source(source: Path) -> tuple[Path, dict[str, str]]:
    """! @brief 고정 SDK revision과 CAP sample source 해시를 검증합니다. """
    workspace = source.parents[3]
    revisions = {
        "ncs_revision": revision(workspace / "nrf"),
        "zephyr_revision": revision(workspace / "zephyr"),
    }
    if revisions["ncs_revision"] != NCS_REVISION:
        raise RuntimeError("fixed NCS revision mismatch")
    if revisions["zephyr_revision"] != ZEPHYR_REVISION:
        raise RuntimeError("fixed Zephyr revision mismatch")
    for relative, expected in SOURCE_HASHES.items():
        if sha256(source / relative) != expected:
            raise RuntimeError(f"fixed CAP Acceptor source hash mismatch: {relative}")
    return workspace, revisions


def prepare(source: Path, destination: Path) -> dict[str, object]:
    """! @brief 원본 밖의 복사본에 Enable 거부와 UART marker를 추가합니다. """
    workspace, revisions = verify_source(source)
    if destination.exists():
        raise FileExistsError(destination)

    shutil.copytree(source, destination)
    header_path = destination / "src/cap_acceptor.h"
    header = header_path.read_text(encoding="utf-8")
    header = replace_once(
        header,
        "#define SINK_CONTEXT        BT_AUDIO_CONTEXT_TYPE_UNSPECIFIED\n",
        "#define SINK_CONTEXT        BT_AUDIO_CONTEXT_TYPE_MEDIA\n",
    )
    header_path.write_text(header, encoding="utf-8", newline="\n")

    unicast_path = destination / "src/cap_acceptor_unicast.c"
    unicast = unicast_path.read_text(encoding="utf-8")
    unicast = replace_once(
        unicast,
        "static int unicast_server_enable_cb(struct bt_bap_stream *bap_stream, const uint8_t meta[],\n"
        "\t\t\t\t    size_t meta_len, struct bt_bap_ascs_rsp *rsp)\n"
        "{\n"
        "\tLOG_INF(\"Enable: bap_stream %p meta_len %zu\", bap_stream, meta_len);\n\n"
        "\treturn 0;\n"
        "}\n",
        "/** @brief CAP 시작의 Enable을 원격 ASCS 오류로 의도적으로 거부합니다. */\n"
        "static int unicast_server_enable_cb(struct bt_bap_stream *bap_stream, const uint8_t meta[],\n"
        "                                    size_t meta_len, struct bt_bap_ascs_rsp *rsp)\n"
        "{\n"
        "    ARG_UNUSED(bap_stream);\n"
        "    ARG_UNUSED(meta);\n"
        "    ARG_UNUSED(meta_len);\n"
        "    *rsp = BT_BAP_ASCS_RSP(BT_BAP_ASCS_RSP_CODE_METADATA_REJECTED,\n"
        "                           BT_AUDIO_METADATA_TYPE_STREAM_CONTEXT);\n"
        "    printk(\"M31_CAP_REJECT_ENABLE code=%u reason=%u\\n\", rsp->code, rsp->reason);\n"
        "    return -EINVAL;\n"
        "}\n",
    )
    unicast_path.write_text(unicast, encoding="utf-8", newline="\n")

    main_path = destination / "src/main.c"
    main = main_path.read_text(encoding="utf-8")
    main = replace_once(
        main,
        "\tLOG_INF(\"Bluetooth initialized\");\n",
        "\tLOG_INF(\"Bluetooth initialized\");\n\n"
        "    /** @brief 반복 시험에서 이전 bond가 보안 절차에 영향을 주지 않게 합니다. */\n"
        "    bt_set_bondable(false);\n",
    )
    main = replace_once(
        main,
        "\tLOG_INF(\"Advertising successfully started\");\n",
        "\tLOG_INF(\"Advertising successfully started\");\n"
        "    printk(\"M31_CAP_REJECT_READY mode=enable\\n\");\n",
    )
    main_path.write_text(main, encoding="utf-8", newline="\n")

    config_path = destination / "prj.conf"
    config = config_path.read_text(encoding="utf-8")
    config = replace_once(
        config,
        'CONFIG_BT_DEVICE_NAME="CAP Acceptor"\n',
        'CONFIG_BT_DEVICE_NAME="M31 CAP Reject"\n',
    )
    config_path.write_text(config, encoding="utf-8", newline="\n")

    generated_hashes = {
        relative: sha256(destination / relative)
        for relative in SOURCE_HASHES
    }
    return {
        **revisions,
        "workspace": str(workspace),
        "source": str(source),
        "source_sha256": SOURCE_HASHES,
        "generated_sha256": generated_hashes,
        "injection": {
            "operation": "ASCS Enable",
            "response_code": 11,
            "response_reason": 2,
            "initiator_native_error": -77,
            "initiator_failed_on_peer": True,
            "sink_context": "media",
        },
    }


def main() -> None:
    """! @brief 명령행 인자를 검증하고 외부 fixture 복사본과 기록을 만듭니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--record", required=True, type=Path)
    arguments = parser.parse_args()
    record = prepare(arguments.source.resolve(), arguments.destination.resolve())
    arguments.record.parent.mkdir(parents=True, exist_ok=True)
    arguments.record.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print("M31_CAP_REJECT_FIXTURE_PREPARED")


if __name__ == "__main__":
    main()
