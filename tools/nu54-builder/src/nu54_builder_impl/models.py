"""! @brief 외부 JSON 형식을 바꾸지 않는 builder 내부 필수 field 모델입니다. """
from pathlib import Path
from typing import Any, NotRequired, TypedDict


class ProductIdentity(TypedDict):
    """! @brief 소스 버전과 설치 배포 버전의 서로 다른 의미입니다. """
    source_version: str
    package_version: str


class ToolEnvironment(TypedDict):
    """! @brief 검증된 SDK와 실행 파일·하위 process 환경입니다. """
    ncs_root: Path
    toolchain_root: Path
    zephyr_base: Path
    environment: dict[str, str]
    west: Path
    git: Path
    compiler: Path
    size: Path
    ccache: Path | None
    ccache_root: Path


class BuildContext(TypedDict):
    """! @brief configure 필수 field와 link 갱신 field를 구분합니다. """
    schema_version: int
    adapter_version: str
    product_identity: ProductIdentity
    state: str
    fqbn: str
    board: str
    profile: str
    sysbuild: bool
    ncs_version: str
    zephyr_version: str
    platform_root: str
    board_root: str
    sketch_root: str
    build_path: str
    cache_schema_version: int
    cache_key: str
    cache_root: str
    cache_dir: str
    input_manifest: str
    app_dir: str
    zephyr_build_dir: str
    ncs_root: str
    toolchain_root: str
    toolchain_bundle_id: str
    cxx_compiler: str
    size_tool: str
    ccache: str | None
    ccache_dir: str
    configuration_fingerprint: str
    configure_mode: str
    configure_reason: str
    configure_duration_seconds: float
    configure_skipped: bool
    cache_reused: bool
    pristine_configure_count: int
    recovery_count: int
    updated_at_utc: str
    source_manifest_changed: NotRequired[bool]
    link_configure_duration_seconds: NotRequired[float]
    build_duration_seconds: NotRequired[float]
    ccache_stats_before: NotRequired[dict[str, int]]
    ccache_stats_after: NotRequired[dict[str, int]]
    ccache_stats_delta: NotRequired[dict[str, int]]
    memory_layout: NotRequired[dict[str, Any]]
    selected_library_features: NotRequired[list[dict[str, Any]]]


class ArtifactManifest(TypedDict):
    """! @brief publication 마지막에 공개하는 기존 artifact JSON입니다. """
    schema_version: int
    adapter_version: str
    product_identity: ProductIdentity
    fqbn: str
    board: str
    sysbuild: bool
    cache: dict[str, Any]
    metrics: dict[str, Any]
    context: BuildContext
    sources: list[str]
    source_inputs: dict[str, Any]
    artifacts: dict[str, Any]
    built_at_utc: str
