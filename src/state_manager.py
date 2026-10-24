import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from src.models.schemas import SeedanceConfig, SuperResolutionConfig

PART_KEYS = [f"part{index}" for index in range(1, 7)]
STATE_FILENAME = "state.json"


class StateError(RuntimeError):
    pass


def load_or_create_state(output_dir: Path, seedance_config: SeedanceConfig, run_mode: str) -> dict[str, Any]:
    state_path = output_dir / STATE_FILENAME
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state = _ensure_state_shape(output_dir, state, seedance_config)
    else:
        state = create_initial_state(output_dir, seedance_config)

    state["last_run_mode"] = run_mode
    state["updated_at"] = _now_text()
    save_state(output_dir, state)
    return state


def create_initial_state(output_dir: Path, seedance_config: SeedanceConfig) -> dict[str, Any]:
    menu = _read_menu(output_dir)
    now = _now_text()
    return {
        "menu": menu,
        "folder_name": output_dir.name,
        "created_at": now,
        "updated_at": now,
        "last_run_mode": None,
        "prompt_full_path": "prompt_full.txt",
        "reference_image_path": _relative_or_name(output_dir, seedance_config.reference_image_path),
        "reference_prompt_prefix_enabled": True,
        "seedance_config_snapshot": {
            "model": seedance_config.model,
            "ratio": seedance_config.ratio,
            "resolution": seedance_config.resolution,
            "duration": seedance_config.duration,
            "generate_audio": seedance_config.generate_audio,
            "watermark": seedance_config.watermark,
            "reference_image_role": seedance_config.reference_image_role,
        },
        "parts": {
            part_key: {
                "status": "pending",
                "prompt_path": f"{part_key}_prompt.txt",
                "task_id": None,
                "video_url": None,
                "video_path": None,
                "error": None,
                "debug_seedance_prompt_path": None,
                "is_mock_video": False,
            }
            for part_key in PART_KEYS
        },
    }


def save_state(output_dir: Path, state: dict[str, Any]) -> Path:
    state["updated_at"] = _now_text()
    path = output_dir / STATE_FILENAME
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_state(output_dir: Path) -> dict[str, Any]:
    state_path = output_dir / STATE_FILENAME
    if not state_path.exists():
        raise StateError(f"state.json 不存在：{state_path}")
    return json.loads(state_path.read_text(encoding="utf-8"))


def update_compose(
    output_dir: Path,
    state: dict[str, Any],
    *,
    status: str,
    output_path: str | None,
    error: str | None,
) -> None:
    state["compose"] = {
        "status": status,
        "output_path": output_path,
        "error": error,
    }
    save_state(output_dir, state)


def ensure_super_resolution_state(
    output_dir: Path,
    state: dict[str, Any],
    super_resolution_config: SuperResolutionConfig,
) -> dict[str, Any]:
    state.setdefault(
        "super_resolution_parts",
        create_initial_super_resolution_state(super_resolution_config),
    )
    super_resolution_state = state["super_resolution_parts"]
    super_resolution_state.setdefault("status", "pending")
    super_resolution_state["task_type"] = super_resolution_config.task_type
    super_resolution_state["target_resolution"] = super_resolution_config.target_resolution
    super_resolution_state.setdefault("parts", {})

    initial = create_initial_super_resolution_state(super_resolution_config)
    for part_key in PART_KEYS:
        super_resolution_state["parts"].setdefault(part_key, {})
        for key, value in initial["parts"][part_key].items():
            super_resolution_state["parts"][part_key].setdefault(key, value)

    save_state(output_dir, state)
    return state


def create_initial_super_resolution_state(
    super_resolution_config: SuperResolutionConfig,
) -> dict[str, Any]:
    return {
        "status": "pending",
        "task_type": super_resolution_config.task_type,
        "target_resolution": super_resolution_config.target_resolution,
        "parts": {
            part_key: {
                "status": "pending",
                "source_video_url": None,
                "task_id": None,
                "output_video_url": None,
                "output_path": None,
                "error": None,
                "is_mock_super_resolution": False,
            }
            for part_key in PART_KEYS
        },
    }


def update_super_resolution_part(
    output_dir: Path,
    state: dict[str, Any],
    part_key: str,
    **updates: Any,
) -> None:
    if "super_resolution_parts" not in state:
        raise StateError("state.json 中不存在 super_resolution_parts")
    parts = state["super_resolution_parts"].get("parts")
    if not isinstance(parts, dict) or part_key not in parts:
        raise StateError(f"state.json 中不存在超分 part：{part_key}")
    parts[part_key].update(updates)
    save_state(output_dir, state)


def update_super_resolution_root(
    output_dir: Path,
    state: dict[str, Any],
    **updates: Any,
) -> None:
    state.setdefault("super_resolution_parts", {})
    state["super_resolution_parts"].update(updates)
    save_state(output_dir, state)


def update_compose_upscaled(
    output_dir: Path,
    state: dict[str, Any],
    *,
    status: str,
    output_path: str | None,
    error: str | None,
) -> None:
    state["compose_upscaled"] = {
        "status": status,
        "output_path": output_path,
        "error": error,
    }
    save_state(output_dir, state)


def update_part(
    output_dir: Path,
    state: dict[str, Any],
    part_key: str,
    **updates: Any,
) -> None:
    if part_key not in state["parts"]:
        raise StateError(f"state.json 中不存在 part：{part_key}")
    state["parts"][part_key].update(updates)
    save_state(output_dir, state)


def can_skip_done_part(output_dir: Path, part_key: str, part_state: dict[str, Any], mock_video: bool) -> bool:
    video_path_value = part_state.get("video_path") or f"{part_key}.mp4"
    video_path = output_dir / video_path_value
    if part_state.get("status") != "done" or not video_path.exists():
        return False

    is_mock_video = bool(part_state.get("is_mock_video"))
    if mock_video:
        return is_mock_video
    return not is_mock_video


def mark_skipped(output_dir: Path, state: dict[str, Any], part_key: str) -> None:
    update_part(output_dir, state, part_key, status="skipped", error=None)


def restore_skipped_to_done(output_dir: Path, state: dict[str, Any], part_key: str) -> None:
    update_part(output_dir, state, part_key, status="done", error=None)


def _ensure_state_shape(
    output_dir: Path,
    state: dict[str, Any],
    seedance_config: SeedanceConfig,
) -> dict[str, Any]:
    normalized = deepcopy(state)
    initial = create_initial_state(output_dir, seedance_config)

    for key, value in initial.items():
        normalized.setdefault(key, value)

    normalized.setdefault("parts", {})
    for part_key in PART_KEYS:
        normalized["parts"].setdefault(part_key, {})
        for key, value in initial["parts"][part_key].items():
            normalized["parts"][part_key].setdefault(key, value)

    normalized["reference_image_path"] = initial["reference_image_path"]
    normalized["reference_prompt_prefix_enabled"] = True
    normalized["seedance_config_snapshot"] = initial["seedance_config_snapshot"]
    return normalized


def _read_menu(output_dir: Path) -> list[str]:
    menu_path = output_dir / "menu.txt"
    if not menu_path.exists():
        return []
    return [
        line.strip()
        for line in menu_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _relative_or_name(output_dir: Path, path: Path) -> str:
    try:
        return path.relative_to(output_dir).as_posix()
    except ValueError:
        try:
            return path.relative_to(output_dir.parent.parent).as_posix()
        except ValueError:
            return path.as_posix()


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
