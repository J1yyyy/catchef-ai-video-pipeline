from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.clients.aimediakit_client import (
    AIMediaKitClient,
    AIMediaKitClientError,
    extract_output_video_url,
)
from src.logger import log, log_error
from src.models.schemas import AppConfig
from src.state_manager import (
    PART_KEYS,
    ensure_super_resolution_state,
    load_state,
    update_super_resolution_part,
    update_super_resolution_root,
)


class SuperResolutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class SuperResolutionSummary:
    success_count: int
    failed_count: int
    skipped_count: int


def run_super_resolution_for_output_dir(
    output_dir: Path,
    config: AppConfig,
    mock_super_resolution: bool,
    resume: bool,
    selected_parts: list[int] | None = None,
) -> SuperResolutionSummary:
    output_dir = output_dir.resolve()
    if not output_dir.exists():
        raise SuperResolutionError(f"输出文件夹不存在：{output_dir}")
    if not output_dir.is_dir():
        raise SuperResolutionError(f"输出路径不是文件夹：{output_dir}")
    if not config.super_resolution.enabled:
        log("config.yaml 中 super_resolution.enabled 为 false；本次已通过命令显式触发超分，将继续执行")

    state = load_state(output_dir)
    ensure_super_resolution_state(output_dir, state, config.super_resolution)
    part_keys = _resolve_part_keys(selected_parts)

    client: AIMediaKitClient | None = None
    if not mock_super_resolution:
        client = AIMediaKitClient(config.super_resolution)

    success_count = 0
    failed_count = 0
    skipped_count = 0

    log(f"当前输出文件夹：{output_dir}")
    log(f"当前是否 mock_super_resolution：{mock_super_resolution}")
    log("当前处理 parts：" + ",".join(part_key.replace("part", "") for part_key in part_keys))

    for part_key in part_keys:
        log(f"当前超分处理 {part_key}")
        part_result = _run_super_resolution_part(
            output_dir=output_dir,
            state=state,
            config=config,
            part_key=part_key,
            mock_super_resolution=mock_super_resolution,
            resume=resume,
            client=client,
        )
        if part_result == "success":
            success_count += 1
        elif part_result == "skipped":
            skipped_count += 1
        else:
            failed_count += 1

    update_super_resolution_root(
        output_dir,
        state,
        status=_resolve_root_status(state),
    )
    log(f"超分汇总：成功 {success_count} 个，失败 {failed_count} 个，跳过 {skipped_count} 个")
    return SuperResolutionSummary(
        success_count=success_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
    )


def _run_super_resolution_part(
    output_dir: Path,
    state: dict[str, Any],
    config: AppConfig,
    part_key: str,
    mock_super_resolution: bool,
    resume: bool,
    client: AIMediaKitClient | None,
) -> str:
    output_path = output_dir / f"{part_key}_upscaled.mp4"
    super_part = state["super_resolution_parts"]["parts"][part_key]
    source_error = _validate_source_part(output_dir, state, part_key)
    if source_error:
        update_super_resolution_part(
            output_dir,
            state,
            part_key,
            status="failed",
            source_video_url=_get_source_video_url(state, part_key),
            error=source_error,
            is_mock_super_resolution=False,
        )
        log_error(source_error)
        return "failed"

    source_video_url = _get_source_video_url(state, part_key)
    assert source_video_url is not None
    if _can_skip_done_part(output_dir, part_key, super_part, mock_super_resolution):
        log(f"{part_key} 已完成超分且文件存在，本次跳过")
        return "skipped"

    is_mock_result = bool(super_part.get("is_mock_super_resolution"))
    if output_path.exists() and not config.super_resolution.overwrite_existing and not is_mock_result:
        message = (
            f"{output_path.name} 已存在，且 super_resolution.overwrite_existing=false，"
            "不会覆盖旧文件"
        )
        update_super_resolution_part(
            output_dir,
            state,
            part_key,
            status="failed",
            source_video_url=source_video_url,
            error=message,
        )
        log_error(message)
        return "failed"

    if mock_super_resolution:
        _write_mock_super_resolution(output_path, part_key)
        update_super_resolution_part(
            output_dir,
            state,
            part_key,
            status="done",
            source_video_url=source_video_url,
            task_id=f"mock-super-resolution-{part_key}",
            output_video_url=None,
            output_path=output_path.name,
            error=None,
            is_mock_super_resolution=True,
        )
        log(f"{part_key} mock 超分占位文件已保存：{output_path}")
        return "success"

    assert client is not None
    try:
        return _run_real_super_resolution_part(
            output_dir=output_dir,
            state=state,
            config=config,
            part_key=part_key,
            source_video_url=source_video_url,
            output_path=output_path,
            client=client,
            resume=resume,
        )
    except Exception as exc:
        current_super_part = state["super_resolution_parts"]["parts"][part_key]
        task_id = current_super_part.get("task_id")
        status = current_super_part.get("status") if task_id else "failed"
        update_super_resolution_part(
            output_dir,
            state,
            part_key,
            status=status,
            source_video_url=source_video_url,
            error=str(exc),
            is_mock_super_resolution=False,
        )
        log_error(f"{part_key} 超分失败：{exc}")
        return "failed"


def _run_real_super_resolution_part(
    output_dir: Path,
    state: dict[str, Any],
    config: AppConfig,
    part_key: str,
    source_video_url: str,
    output_path: Path,
    client: AIMediaKitClient,
    resume: bool,
) -> str:
    super_part = state["super_resolution_parts"]["parts"][part_key]
    output_video_url = super_part.get("output_video_url")
    if output_video_url and not output_path.exists():
        log(f"{part_key} 已有 output_video_url，先尝试继续下载")
        _download_success_video(output_dir, state, part_key, output_video_url, output_path, client)
        return "success"

    task_id = super_part.get("task_id")
    if task_id:
        log(f"{part_key} 已有超分 task_id，先查询旧任务：{task_id}")
        status, response = client.poll_until_finished(task_id)
        if status == "done":
            return _download_from_success_response(output_dir, state, part_key, response, output_path, client)

        final_status = "expired" if status == "expired" else "failed"
        update_super_resolution_part(
            output_dir,
            state,
            part_key,
            status=final_status,
            source_video_url=source_video_url,
            error=f"超分任务状态为 {status}，完整响应：{response}",
            is_mock_super_resolution=False,
        )
        log_error(f"{part_key} 超分任务失败：{status}")
        return "failed"

    if resume:
        log(f"{part_key} 没有可续跑的超分 task_id，将提交新任务")

    task_id, _ = client.create_enhance_task(source_video_url)
    update_super_resolution_part(
        output_dir,
        state,
        part_key,
        status="running",
        source_video_url=source_video_url,
        task_id=task_id,
        output_video_url=None,
        output_path=None,
        error=None,
        is_mock_super_resolution=False,
    )
    log(f"{part_key} 已创建超分任务，task_id：{task_id}")

    status, response = client.poll_until_finished(task_id)
    if status == "done":
        return _download_from_success_response(output_dir, state, part_key, response, output_path, client)

    final_status = "expired" if status == "expired" else "failed"
    update_super_resolution_part(
        output_dir,
        state,
        part_key,
        status=final_status,
        source_video_url=source_video_url,
        error=f"超分任务状态为 {status}，完整响应：{response}",
        is_mock_super_resolution=False,
    )
    log_error(f"{part_key} 超分任务失败：{status}")
    return "failed"


def _download_from_success_response(
    output_dir: Path,
    state: dict[str, Any],
    part_key: str,
    response: dict[str, Any],
    output_path: Path,
    client: AIMediaKitClient,
) -> str:
    output_video_url = extract_output_video_url(response)
    if not output_video_url:
        raise AIMediaKitClientError(f"超分任务成功但未找到 output_video_url，完整响应：{response}")
    _download_success_video(output_dir, state, part_key, output_video_url, output_path, client)
    return "success"


def _download_success_video(
    output_dir: Path,
    state: dict[str, Any],
    part_key: str,
    output_video_url: str,
    output_path: Path,
    client: AIMediaKitClient,
) -> None:
    super_part = state["super_resolution_parts"]["parts"][part_key]
    update_super_resolution_part(
        output_dir,
        state,
        part_key,
        status=super_part.get("status") or "running",
        source_video_url=super_part.get("source_video_url") or _get_source_video_url(state, part_key),
        task_id=super_part.get("task_id"),
        output_video_url=output_video_url,
        error=None,
        is_mock_super_resolution=False,
    )
    client.download_video(output_video_url, output_path)
    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise AIMediaKitClientError(f"超分下载后文件不存在或大小为 0：{output_path}")
    update_super_resolution_part(
        output_dir,
        state,
        part_key,
        status="done",
        source_video_url=super_part.get("source_video_url") or _get_source_video_url(state, part_key),
        task_id=super_part.get("task_id"),
        output_video_url=output_video_url,
        output_path=output_path.name,
        error=None,
        is_mock_super_resolution=False,
    )
    log(f"{part_key} 超分视频下载成功，保存路径：{output_path}")


def _validate_source_part(output_dir: Path, state: dict[str, Any], part_key: str) -> str | None:
    parts = state.get("parts")
    if not isinstance(parts, dict):
        return "state.json 缺少 parts 字段"
    part_state = parts.get(part_key)
    if not isinstance(part_state, dict):
        return f"{part_key} 在 state.json 中不存在"
    if part_state.get("status") != "done":
        return f"{part_key} 原始视频状态不是 done，当前状态：{part_state.get('status')}"
    if bool(part_state.get("is_mock_video")):
        return f"{part_key} 是 mock 视频，不能超分"
    if not part_state.get("video_url"):
        return f"{part_key} 缺少 video_url，请重新生成该 part 或重新获取 URL 后再超分"

    video_path_value = part_state.get("video_path") or f"{part_key}.mp4"
    video_path = output_dir / video_path_value
    if not video_path.exists():
        return f"{part_key} 原始视频文件不存在：{video_path}"
    return None


def _get_source_video_url(state: dict[str, Any], part_key: str) -> str | None:
    parts = state.get("parts")
    if not isinstance(parts, dict):
        return None
    part_state = parts.get(part_key)
    if not isinstance(part_state, dict):
        return None
    video_url = part_state.get("video_url")
    return str(video_url) if video_url else None


def _can_skip_done_part(
    output_dir: Path,
    part_key: str,
    super_part: dict[str, Any],
    mock_super_resolution: bool,
) -> bool:
    output_path_value = super_part.get("output_path") or f"{part_key}_upscaled.mp4"
    output_path = output_dir / output_path_value
    if super_part.get("status") != "done" or not output_path.exists():
        return False

    is_mock_super_resolution = bool(super_part.get("is_mock_super_resolution"))
    if mock_super_resolution:
        return is_mock_super_resolution
    return not is_mock_super_resolution


def _write_mock_super_resolution(path: Path, part_key: str) -> None:
    path.write_text(
        f"MOCK SUPER RESOLUTION PLACEHOLDER for {part_key}. This is not a playable mp4.\n",
        encoding="utf-8",
    )


def _resolve_root_status(state: dict[str, Any]) -> str:
    parts = state.get("super_resolution_parts", {}).get("parts", {})
    if any(parts.get(part_key, {}).get("status") in {"failed", "expired"} for part_key in PART_KEYS):
        return "failed"
    if all(parts.get(part_key, {}).get("status") == "done" for part_key in PART_KEYS):
        return "done"
    return "pending"


def _resolve_part_keys(selected_parts: list[int] | None) -> list[str]:
    if selected_parts is None:
        return PART_KEYS
    return [f"part{part_number}" for part_number in selected_parts]
