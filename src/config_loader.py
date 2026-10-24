from pathlib import Path
from typing import Any

import yaml

from src.models.schemas import (
    AppConfig,
    ComposeConfig,
    DebugConfig,
    DishesPerVideoConfig,
    LlmConfig,
    PathsConfig,
    RuntimeConfig,
    SeedanceConfig,
    SuperResolutionConfig,
)


class ConfigError(ValueError):
    pass


REQUIRED_KEYS = [
    ("video_count",),
    ("dishes_per_video", "min"),
    ("dishes_per_video", "max"),
    ("parts_per_video",),
    ("duration_per_part",),
    ("paths", "dishes_path"),
    ("paths", "prompt_template_path"),
    ("paths", "output_dir"),
    ("paths", "assets_dir"),
    ("paths", "logs_dir"),
    ("llm", "provider"),
    ("llm", "api_key_env"),
    ("llm", "base_url"),
    ("llm", "model"),
    ("llm", "temperature"),
    ("llm", "max_completion_tokens"),
    ("runtime", "mock_llm"),
    ("runtime", "overwrite_existing"),
    ("seedance", "enabled"),
    ("seedance", "api_key_env"),
    ("seedance", "base_url"),
    ("seedance", "model"),
    ("seedance", "ratio"),
    ("seedance", "resolution"),
    ("seedance", "duration"),
    ("seedance", "generate_audio"),
    ("seedance", "watermark"),
    ("seedance", "reference_image_path"),
    ("seedance", "reference_image_role"),
    ("seedance", "poll_interval_seconds"),
    ("seedance", "max_poll_attempts"),
    ("seedance", "request_timeout_seconds"),
    ("seedance", "max_retries"),
    ("seedance", "mock_video"),
    ("compose", "enabled"),
    ("compose", "output_filename"),
    ("compose", "require_real_video"),
    ("compose", "overwrite_existing"),
    ("super_resolution", "enabled"),
    ("super_resolution", "provider"),
    ("super_resolution", "api_key_env"),
    ("super_resolution", "base_url"),
    ("super_resolution", "submit_path"),
    ("super_resolution", "query_path_template"),
    ("super_resolution", "task_type"),
    ("super_resolution", "target_resolution"),
    ("super_resolution", "mock_super_resolution"),
    ("super_resolution", "overwrite_existing"),
    ("super_resolution", "poll_interval_seconds"),
    ("super_resolution", "max_poll_attempts"),
    ("super_resolution", "request_timeout_seconds"),
    ("super_resolution", "max_retries"),
    ("debug", "save_seedance_prompt"),
]

DEFAULT_REFERENCE_PROMPT_PREFIX = (
    "只参考参考图里的橘猫形象，其他内容都不用参考。"
    "请保持同一只拟人化直立橘猫的外观：橘色长毛、圆脸、大眼睛、毛茸茸尾巴、蓝色牛仔围裙。"
    "不要参考图片里的背景、姿势、构图、光线或道具。视频内容以当前文字提示词为准。"
)


def load_config(config_path: str | Path) -> AppConfig:
    path = Path(config_path).resolve()
    if not path.exists():
        raise ConfigError(f"配置文件不存在：{path}")

    with path.open("r", encoding="utf-8") as file:
        raw_config = yaml.safe_load(file) or {}

    _validate_required_keys(raw_config)

    project_root = path.parent
    dishes_per_video = DishesPerVideoConfig(
        min=int(raw_config["dishes_per_video"]["min"]),
        max=int(raw_config["dishes_per_video"]["max"]),
    )
    if dishes_per_video.min <= 0 or dishes_per_video.max < dishes_per_video.min:
        raise ConfigError("dishes_per_video 配置无效：max 必须大于等于 min，且 min 必须大于 0")

    parts_per_video = int(raw_config["parts_per_video"])
    duration_per_part = int(raw_config["duration_per_part"])
    if parts_per_video != 6:
        raise ConfigError("第一版只支持 parts_per_video: 6")
    if duration_per_part != 15:
        raise ConfigError("第一版只支持 duration_per_part: 15")

    paths_raw = raw_config["paths"]
    paths = PathsConfig(
        dishes_path=_resolve_project_path(project_root, paths_raw["dishes_path"]),
        prompt_template_path=_resolve_project_path(project_root, paths_raw["prompt_template_path"]),
        output_dir=_resolve_project_path(project_root, paths_raw["output_dir"]),
        assets_dir=_resolve_project_path(project_root, paths_raw["assets_dir"]),
        logs_dir=_resolve_project_path(project_root, paths_raw["logs_dir"]),
    )

    llm_raw = raw_config["llm"]
    llm = LlmConfig(
        provider=str(llm_raw["provider"]),
        api_key_env=str(llm_raw["api_key_env"]),
        base_url=str(llm_raw["base_url"]),
        model=str(llm_raw["model"]),
        temperature=float(llm_raw["temperature"]),
        max_completion_tokens=int(llm_raw["max_completion_tokens"]),
    )

    runtime_raw = raw_config["runtime"]
    runtime = RuntimeConfig(
        mock_llm=bool(runtime_raw["mock_llm"]),
        overwrite_existing=bool(runtime_raw["overwrite_existing"]),
    )

    seedance_raw = raw_config["seedance"]
    seedance = SeedanceConfig(
        enabled=bool(seedance_raw["enabled"]),
        api_key_env=str(seedance_raw["api_key_env"]),
        base_url=str(seedance_raw["base_url"]),
        model=str(seedance_raw["model"]),
        ratio=str(seedance_raw["ratio"]),
        resolution=str(seedance_raw["resolution"]),
        duration=int(seedance_raw["duration"]),
        generate_audio=bool(seedance_raw["generate_audio"]),
        watermark=bool(seedance_raw["watermark"]),
        reference_image_path=_resolve_project_path(project_root, seedance_raw["reference_image_path"]),
        reference_image_role=str(seedance_raw["reference_image_role"]),
        reference_prompt_prefix=str(
            seedance_raw.get("reference_prompt_prefix") or DEFAULT_REFERENCE_PROMPT_PREFIX
        ),
        poll_interval_seconds=int(seedance_raw["poll_interval_seconds"]),
        max_poll_attempts=int(seedance_raw["max_poll_attempts"]),
        request_timeout_seconds=int(seedance_raw["request_timeout_seconds"]),
        max_retries=int(seedance_raw["max_retries"]),
        mock_video=bool(seedance_raw["mock_video"]),
    )
    if seedance.duration != 15:
        raise ConfigError("当前版本只支持 seedance.duration: 15")

    compose_raw = raw_config["compose"]
    compose = ComposeConfig(
        enabled=bool(compose_raw["enabled"]),
        output_filename=str(compose_raw["output_filename"]),
        require_real_video=bool(compose_raw["require_real_video"]),
        overwrite_existing=bool(compose_raw["overwrite_existing"]),
    )
    if not compose.output_filename.strip():
        raise ConfigError("compose.output_filename 不能为空")

    super_resolution_raw = raw_config["super_resolution"]
    super_resolution = SuperResolutionConfig(
        enabled=bool(super_resolution_raw["enabled"]),
        provider=str(super_resolution_raw["provider"]),
        api_key_env=str(super_resolution_raw["api_key_env"]),
        base_url=str(super_resolution_raw["base_url"]),
        submit_path=str(super_resolution_raw["submit_path"]),
        query_path_template=str(super_resolution_raw["query_path_template"]),
        task_type=str(super_resolution_raw["task_type"]),
        target_resolution=str(super_resolution_raw["target_resolution"]),
        mock_super_resolution=bool(super_resolution_raw["mock_super_resolution"]),
        overwrite_existing=bool(super_resolution_raw["overwrite_existing"]),
        poll_interval_seconds=int(super_resolution_raw["poll_interval_seconds"]),
        max_poll_attempts=int(super_resolution_raw["max_poll_attempts"]),
        request_timeout_seconds=int(super_resolution_raw["request_timeout_seconds"]),
        max_retries=int(super_resolution_raw["max_retries"]),
    )
    _validate_super_resolution_config(super_resolution)

    debug_raw = raw_config["debug"]
    debug = DebugConfig(
        save_seedance_prompt=bool(debug_raw["save_seedance_prompt"]),
    )

    return AppConfig(
        project_root=project_root,
        video_count=int(raw_config["video_count"]),
        dishes_per_video=dishes_per_video,
        parts_per_video=parts_per_video,
        duration_per_part=duration_per_part,
        paths=paths,
        llm=llm,
        runtime=runtime,
        seedance=seedance,
        compose=compose,
        super_resolution=super_resolution,
        debug=debug,
    )


def _validate_required_keys(config: dict[str, Any]) -> None:
    missing_keys = []
    for key_path in REQUIRED_KEYS:
        current = config
        for key in key_path:
            if not isinstance(current, dict) or key not in current:
                missing_keys.append(".".join(key_path))
                break
            current = current[key]

    if missing_keys:
        raise ConfigError("配置文件缺少必要字段：" + ", ".join(missing_keys))


def _resolve_project_path(project_root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return project_root / path


def _validate_super_resolution_config(config: SuperResolutionConfig) -> None:
    if not config.base_url.strip():
        raise ConfigError("super_resolution.base_url 不能为空")
    if not config.submit_path.strip():
        raise ConfigError("super_resolution.submit_path 不能为空")
    if "{task_id}" not in config.query_path_template:
        raise ConfigError("super_resolution.query_path_template 必须包含 {task_id}")
    if not config.task_type.strip():
        raise ConfigError("super_resolution.task_type 不能为空")
    if not config.target_resolution.strip():
        raise ConfigError("super_resolution.target_resolution 不能为空")
    if config.poll_interval_seconds <= 0:
        raise ConfigError("super_resolution.poll_interval_seconds 必须大于 0")
    if config.max_poll_attempts <= 0:
        raise ConfigError("super_resolution.max_poll_attempts 必须大于 0")
    if config.request_timeout_seconds <= 0:
        raise ConfigError("super_resolution.request_timeout_seconds 必须大于 0")
    if config.max_retries <= 0:
        raise ConfigError("super_resolution.max_retries 必须大于 0")
