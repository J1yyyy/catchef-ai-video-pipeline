from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DishesPerVideoConfig:
    min: int
    max: int


@dataclass(frozen=True)
class PathsConfig:
    dishes_path: Path
    prompt_template_path: Path
    output_dir: Path
    assets_dir: Path
    logs_dir: Path


@dataclass(frozen=True)
class LlmConfig:
    provider: str
    api_key_env: str
    base_url: str
    model: str
    temperature: float
    max_completion_tokens: int


@dataclass(frozen=True)
class RuntimeConfig:
    mock_llm: bool
    overwrite_existing: bool


@dataclass(frozen=True)
class SeedanceConfig:
    enabled: bool
    api_key_env: str
    base_url: str
    model: str
    ratio: str
    resolution: str
    duration: int
    generate_audio: bool
    watermark: bool
    reference_image_path: Path
    reference_image_role: str
    reference_prompt_prefix: str
    poll_interval_seconds: int
    max_poll_attempts: int
    request_timeout_seconds: int
    max_retries: int
    mock_video: bool


@dataclass(frozen=True)
class ComposeConfig:
    enabled: bool
    output_filename: str
    require_real_video: bool
    overwrite_existing: bool


@dataclass(frozen=True)
class SuperResolutionConfig:
    enabled: bool
    provider: str
    api_key_env: str
    base_url: str
    submit_path: str
    query_path_template: str
    task_type: str
    target_resolution: str
    mock_super_resolution: bool
    overwrite_existing: bool
    poll_interval_seconds: int
    max_poll_attempts: int
    request_timeout_seconds: int
    max_retries: int


@dataclass(frozen=True)
class DebugConfig:
    save_seedance_prompt: bool


@dataclass(frozen=True)
class AppConfig:
    project_root: Path
    video_count: int
    dishes_per_video: DishesPerVideoConfig
    parts_per_video: int
    duration_per_part: int
    paths: PathsConfig
    llm: LlmConfig
    runtime: RuntimeConfig
    seedance: SeedanceConfig
    compose: ComposeConfig
    super_resolution: SuperResolutionConfig
    debug: DebugConfig


@dataclass(frozen=True)
class VideoRunResult:
    output_dir: Path
    menu: list[str]
    part_files: list[Path]


@dataclass(frozen=True)
class VideoGenerationSummary:
    success_count: int
    failed_count: int
    skipped_count: int
