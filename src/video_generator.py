import time
from pathlib import Path
from typing import Any

from src.clients.seedance_client import (
    SeedanceClient,
    SeedanceClientError,
    extract_status,
    extract_video_url,
)
from src.file_manager import save_text
from src.logger import log, log_error
from src.models.schemas import AppConfig, VideoGenerationSummary
from src.state_manager import (
    PART_KEYS,
    can_skip_done_part,
    load_or_create_state,
    save_state,
    update_part,
)

REFERENCE_PROMPT_PREFIX = (
    "只参考参考图里的橘猫形象，其他内容都不用参考。"
    "请保持同一只拟人化直立橘猫的外观：橘色长毛、圆脸、大眼睛、毛茸茸尾巴、蓝色牛仔围裙。"
    "不要参考图片里的背景、姿势、构图、光线或道具。视频内容以当前文字提示词为准。"
)


class VideoGenerationError(RuntimeError):
    pass


def generate_videos_for_output_dir(
    output_dir: Path,
    config: AppConfig,
    mock_video: bool,
    run_mode: str,
    selected_parts: list[int] | None = None,
) -> VideoGenerationSummary:
    output_dir = output_dir.resolve()
    if not output_dir.exists():
        raise VideoGenerationError(f"输出文件夹不存在：{output_dir}")

    part_keys = _resolve_part_keys(selected_parts)
    _validate_part_prompts(output_dir, part_keys)
    state = load_or_create_state(output_dir, config.seedance, run_mode)
    reference_prefix = config.seedance.reference_prompt_prefix or REFERENCE_PROMPT_PREFIX

    client: SeedanceClient | None = None
    reference_image_data_url: str | None = None
    if not mock_video:
        client = SeedanceClient(config.seedance)
        reference_image_data_url = client.build_reference_image_data_url()

    success_count = 0
    failed_count = 0
    skipped_count = 0

    log(f"当前输出文件夹：{output_dir}")
    log(f"当前是否 mock_video：{mock_video}")
    log("当前处理 parts：" + ",".join(part_key.replace("part", "") for part_key in part_keys))

    for part_key in part_keys:
        part_number = int(part_key.replace("part", ""))
        part_state = state["parts"][part_key]
        log(f"当前处理 {part_key}")
        log(f"当前 part 状态：{part_state.get('status')}")

        if can_skip_done_part(output_dir, part_key, part_state, mock_video=mock_video):
            skipped_count += 1
            log(f"{part_key} 已完成且文件存在，本次跳过")
            continue

        part_prompt_path = output_dir / f"{part_key}_prompt.txt"
        seedance_prompt = _build_seedance_prompt(part_prompt_path, reference_prefix)
        debug_path = output_dir / f"{part_key}_seedance_prompt_debug.txt"

        if config.debug.save_seedance_prompt:
            save_text(debug_path, seedance_prompt)
            update_part(
                output_dir,
                state,
                part_key,
                debug_seedance_prompt_path=debug_path.name,
            )
            log(f"已保存 debug_seedance_prompt_path：{debug_path}")

        if mock_video:
            _write_mock_video(output_dir / f"{part_key}.mp4", part_key)
            update_part(
                output_dir,
                state,
                part_key,
                status="done",
                task_id=f"mock-task-{part_number}",
                video_url=None,
                video_path=f"{part_key}.mp4",
                error=None,
                is_mock_video=True,
            )
            success_count += 1
            log(f"{part_key} mock 视频占位文件已保存：{output_dir / f'{part_key}.mp4'}")
            continue

        assert client is not None
        assert reference_image_data_url is not None

        try:
            part_result = _run_real_video_part(
                output_dir=output_dir,
                state=state,
                part_key=part_key,
                seedance_prompt=seedance_prompt,
                debug_path=debug_path,
                save_debug_prompt=config.debug.save_seedance_prompt,
                client=client,
                reference_image_data_url=reference_image_data_url,
            )
        except Exception as exc:
            _save_debug_prompt_on_failure(output_dir, state, part_key, debug_path, seedance_prompt)
            update_part(
                output_dir,
                state,
                part_key,
                status="failed",
                error=str(exc),
                is_mock_video=False,
            )
            failed_count += 1
            log_error(f"{part_key} 生成失败：{exc}")
            log(f"已保存 debug_seedance_prompt_path：{debug_path}")
            continue

        if part_result:
            success_count += 1
        else:
            failed_count += 1

    save_state(output_dir, state)
    log(f"视频生成汇总：成功 {success_count} 个，失败 {failed_count} 个，跳过 {skipped_count} 个")
    return VideoGenerationSummary(
        success_count=success_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
    )


def _run_real_video_part(
    output_dir: Path,
    state: dict[str, Any],
    part_key: str,
    seedance_prompt: str,
    debug_path: Path,
    save_debug_prompt: bool,
    client: SeedanceClient,
    reference_image_data_url: str,
) -> bool:
    part_state = state["parts"][part_key]
    state_status = part_state.get("status")
    task_id = part_state.get("task_id") if state_status in {"running", "failed"} else None

    if task_id:
        log(f"{part_key} 已有 task_id，先查询旧任务：{task_id}")
        status, response = _poll_task(client, task_id)
        if status == "done":
            return _download_success_video(
                output_dir=output_dir,
                state=state,
                part_key=part_key,
                task_id=task_id,
                response=response,
                debug_path=debug_path,
                save_debug_prompt=save_debug_prompt,
                client=client,
            )

        log_error(f"{part_key} 旧任务状态为 {status}，将重新提交 Seedance 任务")
        update_part(
            output_dir,
            state,
            part_key,
            status="pending",
            error=f"旧任务状态为 {status}，完整响应：{response}",
            is_mock_video=False,
        )

    task_id, _ = client.create_task(seedance_prompt, reference_image_data_url)
    update_part(
        output_dir,
        state,
        part_key,
        status="running",
        task_id=task_id,
        error=None,
        is_mock_video=False,
    )
    log(f"{part_key} 已创建任务，task_id：{task_id}")

    status, response = _poll_task(client, task_id)
    if status == "done":
        return _download_success_video(
            output_dir=output_dir,
            state=state,
            part_key=part_key,
            task_id=task_id,
            response=response,
            debug_path=debug_path,
            save_debug_prompt=save_debug_prompt,
            client=client,
        )

    if status == "expired":
        final_status = "expired"
    else:
        final_status = "failed"

    update_part(
        output_dir,
        state,
        part_key,
        status=final_status,
        error=f"任务状态为 {status}，完整响应：{response}",
        is_mock_video=False,
    )
    _save_debug_prompt_on_failure(output_dir, state, part_key, debug_path, seedance_prompt)
    log_error(f"{part_key} 任务失败：{status}")
    log(f"已保存 debug_seedance_prompt_path：{debug_path}")
    return False


def _download_success_video(
    output_dir: Path,
    state: dict[str, Any],
    part_key: str,
    task_id: str,
    response: dict[str, Any],
    debug_path: Path,
    save_debug_prompt: bool,
    client: SeedanceClient,
) -> bool:
    video_url = extract_video_url(response)
    if not video_url:
        raise SeedanceClientError(f"任务成功但未找到 video_url，完整响应：{response}")

    video_path = output_dir / f"{part_key}.mp4"
    client.download_video(video_url, video_path)
    part_state = state["parts"][part_key]
    update_part(
        output_dir,
        state,
        part_key,
        status="done",
        task_id=task_id,
        video_url=video_url,
        video_path=video_path.name,
        error=None,
        is_mock_video=False,
        debug_seedance_prompt_path=(
            debug_path.name if save_debug_prompt else part_state.get("debug_seedance_prompt_path")
        ),
    )
    log(f"{part_key} 下载成功，保存路径：{video_path}")
    return True


def _poll_task(client: SeedanceClient, task_id: str) -> tuple[str, dict[str, Any]]:
    last_response: dict[str, Any] = {}
    for _ in range(client.config.max_poll_attempts):
        last_response = client.get_task(task_id)
        status = extract_status(last_response)
        if not status:
            raise SeedanceClientError(f"查询任务成功但未找到 status，完整响应：{last_response}")

        normalized_status = status.lower()
        log(f"轮询 task_id={task_id}，当前任务状态：{normalized_status}")
        if normalized_status in client.SUCCESS_STATUSES:
            return "done", last_response
        if normalized_status in client.FAILED_STATUSES:
            return normalized_status, last_response
        if normalized_status not in client.RUNNING_STATUSES:
            raise SeedanceClientError(f"未知任务状态：{status}，完整响应：{last_response}")

        time.sleep(client.config.poll_interval_seconds)

    raise SeedanceClientError(
        f"轮询超过最大次数 {client.config.max_poll_attempts}，最后响应：{last_response}"
    )


def _build_seedance_prompt(part_prompt_path: Path, reference_prefix: str) -> str:
    part_prompt = part_prompt_path.read_text(encoding="utf-8")
    return f"{reference_prefix}\n\n{part_prompt}"


def _save_debug_prompt_on_failure(
    output_dir: Path,
    state: dict[str, Any],
    part_key: str,
    debug_path: Path,
    seedance_prompt: str,
) -> None:
    save_text(debug_path, seedance_prompt)
    update_part(
        output_dir,
        state,
        part_key,
        debug_seedance_prompt_path=debug_path.name,
    )


def _write_mock_video(path: Path, part_key: str) -> None:
    path.write_text(
        f"MOCK VIDEO PLACEHOLDER for {part_key}. This is not a playable mp4.\n",
        encoding="utf-8",
    )


def _resolve_part_keys(selected_parts: list[int] | None) -> list[str]:
    if selected_parts is None:
        return PART_KEYS
    return [f"part{part_number}" for part_number in selected_parts]


def _validate_part_prompts(output_dir: Path, part_keys: list[str]) -> None:
    missing = [
        f"{part_key}_prompt.txt"
        for part_key in part_keys
        if not (output_dir / f"{part_key}_prompt.txt").exists()
    ]
    if missing:
        raise VideoGenerationError("缺少 part prompt 文件：" + ", ".join(missing))
