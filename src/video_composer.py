import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.logger import log
from src.models.schemas import AppConfig
from src.state_manager import PART_KEYS, load_state, update_compose, update_compose_upscaled

CONCAT_LIST_FILENAME = "concat_list.txt"
TEMP_OUTPUT_FILENAME = ".final_90s.tmp.mp4"
UPSCALED_CONCAT_LIST_FILENAME = "concat_list_upscaled.txt"
UPSCALED_TEMP_OUTPUT_FILENAME = ".final_90s_upscaled.tmp.mp4"
UPSCALED_OUTPUT_FILENAME = "final_90s_upscaled.mp4"


class VideoComposeError(RuntimeError):
    pass


@dataclass(frozen=True)
class VideoComposeResult:
    output_path: Path
    method: str


def compose_videos_for_output_dir(output_dir: Path, config: AppConfig) -> VideoComposeResult:
    output_dir = output_dir.resolve()
    if not output_dir.exists():
        raise VideoComposeError(f"输出文件夹不存在：{output_dir}")
    if not output_dir.is_dir():
        raise VideoComposeError(f"输出路径不是文件夹：{output_dir}")
    if not config.compose.enabled:
        raise VideoComposeError("config.yaml 中 compose.enabled 为 false，已禁止本地合成")

    state = load_state(output_dir)
    final_path = output_dir / config.compose.output_filename

    if final_path.exists() and not config.compose.overwrite_existing:
        message = (
            f"{config.compose.output_filename} 已存在，且 compose.overwrite_existing=false，"
            "不会覆盖旧文件"
        )
        update_compose(output_dir, state, status="failed", output_path=None, error=message)
        raise VideoComposeError(message)

    try:
        _validate_ready_to_compose(output_dir, state, require_real_video=config.compose.require_real_video)
        final_path, method = _compose_video_files(
            output_dir=output_dir,
            input_filenames=[f"{part_key}.mp4" for part_key in PART_KEYS],
            output_filename=config.compose.output_filename,
            temp_filename=TEMP_OUTPUT_FILENAME,
            concat_list_filename=CONCAT_LIST_FILENAME,
            overwrite_existing=config.compose.overwrite_existing,
        )

    except Exception as exc:
        _cleanup_temp_file(output_dir / TEMP_OUTPUT_FILENAME)
        update_compose(output_dir, state, status="failed", output_path=None, error=str(exc))
        raise

    update_compose(
        output_dir,
        state,
        status="done",
        output_path=final_path.name,
        error=None,
    )
    log(f"90s 视频合成成功：{final_path}")
    return VideoComposeResult(output_path=final_path, method=method)


def compose_upscaled_videos_for_output_dir(output_dir: Path, config: AppConfig) -> VideoComposeResult:
    output_dir = output_dir.resolve()
    if not output_dir.exists():
        raise VideoComposeError(f"输出文件夹不存在：{output_dir}")
    if not output_dir.is_dir():
        raise VideoComposeError(f"输出路径不是文件夹：{output_dir}")

    state = load_state(output_dir)
    final_path = output_dir / UPSCALED_OUTPUT_FILENAME
    if final_path.exists() and not config.super_resolution.overwrite_existing:
        message = (
            f"{UPSCALED_OUTPUT_FILENAME} 已存在，且 super_resolution.overwrite_existing=false，"
            "不会覆盖旧文件"
        )
        update_compose_upscaled(output_dir, state, status="failed", output_path=None, error=message)
        raise VideoComposeError(message)

    try:
        _validate_ready_to_compose_upscaled(output_dir, state)
        final_path, method = _compose_video_files(
            output_dir=output_dir,
            input_filenames=[f"{part_key}_upscaled.mp4" for part_key in PART_KEYS],
            output_filename=UPSCALED_OUTPUT_FILENAME,
            temp_filename=UPSCALED_TEMP_OUTPUT_FILENAME,
            concat_list_filename=UPSCALED_CONCAT_LIST_FILENAME,
            overwrite_existing=config.super_resolution.overwrite_existing,
        )
    except Exception as exc:
        _cleanup_temp_file(output_dir / UPSCALED_TEMP_OUTPUT_FILENAME)
        update_compose_upscaled(output_dir, state, status="failed", output_path=None, error=str(exc))
        raise

    update_compose_upscaled(
        output_dir,
        state,
        status="done",
        output_path=final_path.name,
        error=None,
    )
    log(f"高清 90s 视频合成成功：{final_path}")
    return VideoComposeResult(output_path=final_path, method=method)


def _validate_ready_to_compose(
    output_dir: Path,
    state: dict[str, Any],
    require_real_video: bool,
) -> None:
    parts = state.get("parts")
    if not isinstance(parts, dict):
        raise VideoComposeError("state.json 缺少 parts 字段")

    problems: list[str] = []
    for part_key in PART_KEYS:
        part_state = parts.get(part_key)
        if not isinstance(part_state, dict):
            problems.append(f"{part_key} 在 state.json 中不存在")
            continue

        status = part_state.get("status")
        if status != "done":
            problems.append(f"{part_key} 状态不是 done，当前状态：{status}")

        is_mock_video = bool(part_state.get("is_mock_video"))
        if require_real_video and is_mock_video:
            problems.append(f"{part_key} 是 mock 视频，不能参与合成")

        part_path = output_dir / f"{part_key}.mp4"
        if not part_path.exists():
            problems.append(f"{part_key}.mp4 不存在：{part_path}")

    if problems:
        raise VideoComposeError("合成条件不满足：\n" + "\n".join(problems))


def _validate_ready_to_compose_upscaled(output_dir: Path, state: dict[str, Any]) -> None:
    super_resolution_state = state.get("super_resolution_parts")
    if not isinstance(super_resolution_state, dict):
        raise VideoComposeError("state.json 缺少 super_resolution_parts 字段")
    parts = super_resolution_state.get("parts")
    if not isinstance(parts, dict):
        raise VideoComposeError("state.json 缺少 super_resolution_parts.parts 字段")

    problems: list[str] = []
    for part_key in PART_KEYS:
        part_state = parts.get(part_key)
        if not isinstance(part_state, dict):
            problems.append(f"{part_key} 在 super_resolution_parts.parts 中不存在")
            continue

        status = part_state.get("status")
        if status != "done":
            problems.append(f"{part_key} 超分状态不是 done，当前状态：{status}")

        if bool(part_state.get("is_mock_super_resolution")):
            problems.append(f"{part_key} 是 mock 超分结果，不能参与高清合成")

        part_path = output_dir / f"{part_key}_upscaled.mp4"
        if not part_path.exists():
            problems.append(f"{part_key}_upscaled.mp4 不存在：{part_path}")

    if problems:
        raise VideoComposeError("高清合成条件不满足：\n" + "\n".join(problems))


def _compose_video_files(
    output_dir: Path,
    input_filenames: list[str],
    output_filename: str,
    temp_filename: str,
    concat_list_filename: str,
    overwrite_existing: bool,
) -> tuple[Path, str]:
    final_path = output_dir / output_filename
    temp_path = output_dir / temp_filename
    concat_list_path = output_dir / concat_list_filename

    if final_path.exists() and not overwrite_existing:
        raise VideoComposeError(f"{output_filename} 已存在，不允许覆盖")

    _cleanup_temp_file(temp_path)
    _write_concat_list(concat_list_path, input_filenames)

    log("开始尝试 FFmpeg 无损拼接：-c copy")
    copy_result = _run_ffmpeg(
        output_dir=output_dir,
        command=[
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_list_filename,
            "-c",
            "copy",
            temp_filename,
        ],
    )
    method = "copy"

    if copy_result.returncode != 0:
        log("无损拼接失败，开始 fallback 到重新编码")
        _cleanup_temp_file(temp_path)
        encode_result = _run_ffmpeg(
            output_dir=output_dir,
            command=[
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                concat_list_filename,
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                temp_filename,
            ],
        )
        method = "reencode"
        if encode_result.returncode != 0:
            error = _format_ffmpeg_error(copy_result.stderr, encode_result.stderr)
            raise VideoComposeError(error)

    _validate_temp_output(temp_path)
    _replace_final_output(temp_path, final_path, overwrite=overwrite_existing)
    if not final_path.exists() or final_path.stat().st_size <= 0:
        raise VideoComposeError(f"合成后文件不存在或大小为 0：{final_path}")
    return final_path, method


def _write_concat_list(path: Path, input_filenames: list[str]) -> None:
    lines = [f"file '{filename}'" for filename in input_filenames]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_ffmpeg(output_dir: Path, command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=output_dir,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise VideoComposeError(
            "找不到 ffmpeg 命令。请先安装 FFmpeg，并确认 ffmpeg 已配置到 PATH"
        ) from exc


def _replace_final_output(temp_path: Path, final_path: Path, overwrite: bool) -> None:
    if final_path.exists():
        if not overwrite:
            raise VideoComposeError(f"{final_path.name} 已存在，不允许覆盖")
        final_path.unlink()
    temp_path.replace(final_path)


def _validate_temp_output(path: Path) -> None:
    if not path.exists() or path.stat().st_size <= 0:
        raise VideoComposeError(f"FFmpeg 未生成有效临时文件：{path}")


def _cleanup_temp_file(path: Path) -> None:
    if path.exists():
        path.unlink()


def _format_ffmpeg_error(copy_stderr: str, encode_stderr: str) -> str:
    copy_tail = _tail_text(copy_stderr)
    encode_tail = _tail_text(encode_stderr)
    return (
        "FFmpeg 无损拼接和重新编码都失败。\n"
        f"无损拼接错误：{copy_tail}\n"
        f"重新编码错误：{encode_tail}"
    )


def _tail_text(text: str, max_lines: int = 12) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return "无错误输出"
    return "\n".join(lines[-max_lines:])
