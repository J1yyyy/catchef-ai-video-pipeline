import argparse
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from src.config_loader import ConfigError, load_config
from src.file_manager import (
    create_output_dir,
    save_filled_prompt,
    save_menu,
    save_part_prompts,
    save_prompt_full,
    save_prompt_raw_failed,
)
from src.logger import log, log_error
from src.menu_selector import MenuError, load_dishes, select_menu
from src.prompt_builder import PromptTemplateError, build_prompt
from src.prompt_generator import generate_prompt
from src.prompt_splitter import PromptSplitError, split_prompt_parts
from src.state_manager import load_or_create_state
from src.super_resolution import SuperResolutionError, run_super_resolution_for_output_dir
from src.video_composer import (
    VideoComposeError,
    compose_upscaled_videos_for_output_dir,
    compose_videos_for_output_dir,
)
from src.video_generator import VideoGenerationError, generate_videos_for_output_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量生成拟人橘猫做印尼菜 AI 视频提示词")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径，默认：config.yaml")
    parser.add_argument("--video-count", type=int, default=None, help="覆盖 config.yaml 里的 video_count")
    parser.add_argument("--mock-llm", action="store_true", help="使用 mock 模式，不调用真实大语言模型 API")
    parser.add_argument("--prompt-only", action="store_true", help="只生成提示词，不生成视频")
    parser.add_argument("--with-video", action="store_true", help="生成提示词后继续生成视频")
    parser.add_argument("--generate-video", help="对已有输出文件夹生成视频")
    parser.add_argument("--resume", help="续跑已有输出文件夹的视频生成")
    parser.add_argument("--compose", help="对已有输出文件夹执行本地 90s 视频拼接")
    parser.add_argument("--super-res-parts", help="对已有输出文件夹的 part 视频分别执行超分")
    parser.add_argument("--resume-super-res-parts", help="续跑已有输出文件夹的 part 视频超分")
    parser.add_argument("--compose-upscaled", help="对已有输出文件夹执行本地高清 90s 视频拼接")
    parser.add_argument("--mock-video", action="store_true", help="使用 mock 视频模式，不调用 Seedance API")
    parser.add_argument("--real-video", action="store_true", help="允许真实调用 Seedance API")
    parser.add_argument("--mock-super-res", action="store_true", help="使用 mock 超分模式，不调用 AI MediaKit API")
    parser.add_argument("--real-super-res", action="store_true", help="允许真实调用 AI MediaKit API")
    parser.add_argument("--parts", default="all", help="指定要处理的 part，例如：1、1,2、1,2,3、all，默认：all")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if load_dotenv is not None:
        load_dotenv()

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        log_error(str(exc))
        return 1

    mode = _resolve_mode(args)
    log(f"当前运行模式：{mode}")

    if mode == "compose":
        output_dir = _resolve_output_dir(config.project_root, args.compose)
        try:
            result = compose_videos_for_output_dir(output_dir=output_dir, config=config)
        except VideoComposeError as exc:
            log_error(str(exc))
            return 1
        except Exception as exc:
            log_error(f"90s 视频合成失败：{exc}")
            return 1
        log(f"合成方式：{result.method}")
        log(f"最终视频路径：{result.output_path}")
        return 0

    if mode == "compose-upscaled":
        output_dir = _resolve_output_dir(config.project_root, args.compose_upscaled)
        try:
            result = compose_upscaled_videos_for_output_dir(output_dir=output_dir, config=config)
        except VideoComposeError as exc:
            log_error(str(exc))
            return 1
        except Exception as exc:
            log_error(f"高清 90s 视频合成失败：{exc}")
            return 1
        log(f"合成方式：{result.method}")
        log(f"最终高清视频路径：{result.output_path}")
        return 0

    mock_video = _resolve_mock_video(args)
    mock_super_resolution = _resolve_mock_super_resolution(args)
    try:
        selected_parts = _parse_parts(args.parts)
    except ValueError as exc:
        log_error(str(exc))
        return 1

    if mode in {"with-video", "generate-video", "resume"}:
        log(f"当前是否 mock_video：{mock_video}")
        log("当前处理 parts：" + ",".join(str(part) for part in selected_parts))
        if not mock_video and not args.real_video:
            log_error("真实 Seedance 调用必须显式传入 --real-video")
            return 1

    if mode in {"super-res-parts", "resume-super-res-parts"}:
        log(f"当前是否 mock_super_resolution：{mock_super_resolution}")
        log("当前处理 parts：" + ",".join(str(part) for part in selected_parts))

    if mode in {"generate-video", "resume"}:
        output_dir_arg = args.generate_video or args.resume
        output_dir = _resolve_output_dir(config.project_root, output_dir_arg)
        try:
            generate_videos_for_output_dir(
                output_dir=output_dir,
                config=config,
                mock_video=mock_video,
                run_mode="mock-video" if mock_video else "real-video",
                selected_parts=selected_parts,
            )
        except VideoGenerationError as exc:
            log_error(str(exc))
            return 1
        except Exception as exc:
            log_error(f"视频生成失败：{exc}")
            return 1
        return 0

    if mode in {"super-res-parts", "resume-super-res-parts"}:
        output_dir_arg = args.super_res_parts or args.resume_super_res_parts
        output_dir = _resolve_output_dir(config.project_root, output_dir_arg)
        try:
            summary = run_super_resolution_for_output_dir(
                output_dir=output_dir,
                config=config,
                mock_super_resolution=mock_super_resolution,
                resume=(mode == "resume-super-res-parts"),
                selected_parts=selected_parts,
            )
        except SuperResolutionError as exc:
            log_error(str(exc))
            return 1
        except Exception as exc:
            log_error(f"视频超分失败：{exc}")
            return 1
        return 1 if summary.failed_count else 0

    try:
        output_dirs = generate_prompt_outputs(config, args.video_count, args.mock_llm, mode)
    except (ConfigError, MenuError) as exc:
        log_error(str(exc))
        return 1

    if not output_dirs:
        return 1

    if mode != "with-video":
        return 0

    has_failure = False
    for output_dir in output_dirs:
        try:
            summary = generate_videos_for_output_dir(
                output_dir=output_dir,
                config=config,
                mock_video=mock_video,
                run_mode="mock-video" if mock_video else "real-video",
                selected_parts=selected_parts,
            )
            if summary.failed_count:
                has_failure = True
        except Exception as exc:
            has_failure = True
            log_error(f"视频生成失败：{exc}")

    return 1 if has_failure else 0


def generate_prompt_outputs(
    config,
    video_count_override: int | None,
    force_mock_llm: bool,
    run_mode: str,
) -> list[Path]:
    dishes = load_dishes(config.paths.dishes_path)
    video_count = video_count_override if video_count_override is not None else config.video_count
    if video_count <= 0:
        raise ConfigError("video_count 必须大于 0")

    mock_llm = force_mock_llm or config.runtime.mock_llm
    success_count = 0
    output_dirs: list[Path] = []

    for index in range(1, video_count + 1):
        log(f"当前生成第 {index}/{video_count} 条完整视频")

        try:
            menu = select_menu(
                dishes,
                min_count=config.dishes_per_video.min,
                max_count=config.dishes_per_video.max,
            )
            log("本次随机菜单：" + "、".join(menu))
            log(f"是否使用 mock_llm：{mock_llm}")

            output_dir = create_output_dir(config.paths.output_dir, menu)
            log(f"输出文件夹路径：{output_dir}")

            save_menu(output_dir, menu)
            filled_prompt = build_prompt(config.paths.prompt_template_path, menu)
            save_filled_prompt(output_dir, filled_prompt)
            log("已成功生成 filled_prompt.txt")

            prompt_full = generate_prompt(filled_prompt, config.llm, mock_llm=mock_llm)
            save_prompt_full(output_dir, prompt_full)
            log("已成功生成 prompt_full.txt")

            try:
                parts = split_prompt_parts(prompt_full)
            except PromptSplitError as exc:
                save_prompt_raw_failed(output_dir, prompt_full)
                log_error(str(exc))
                log_error(f"原始输出已保存为：{output_dir / 'prompt_raw_failed.txt'}")
                continue

            save_part_prompts(output_dir, parts)
            log("已成功分割 part1-part6")
            load_or_create_state(output_dir, config.seedance, run_mode)
            log(f"最终保存路径：{output_dir}")
            success_count += 1
            output_dirs.append(output_dir)

        except (MenuError, PromptTemplateError) as exc:
            log_error(str(exc))
        except Exception as exc:
            log_error(f"第 {index} 条视频生成失败：{exc}")

    if success_count == 0:
        return []

    log(f"运行完成：成功 {success_count}/{video_count} 条")
    return output_dirs


def _resolve_mode(args: argparse.Namespace) -> str:
    selected_modes = [
        bool(args.prompt_only),
        bool(args.with_video),
        bool(args.generate_video),
        bool(args.resume),
        bool(args.compose),
        bool(args.super_res_parts),
        bool(args.resume_super_res_parts),
        bool(args.compose_upscaled),
    ]
    if sum(selected_modes) > 1:
        raise SystemExit(
            "只能选择一种运行模式：--prompt-only / --with-video / --generate-video / --resume / "
            "--compose / --super-res-parts / --resume-super-res-parts / --compose-upscaled"
        )
    if args.with_video:
        return "with-video"
    if args.generate_video:
        return "generate-video"
    if args.resume:
        return "resume"
    if args.compose:
        return "compose"
    if args.super_res_parts:
        return "super-res-parts"
    if args.resume_super_res_parts:
        return "resume-super-res-parts"
    if args.compose_upscaled:
        return "compose-upscaled"
    return "prompt-only"


def _resolve_mock_video(args: argparse.Namespace) -> bool:
    if args.real_video and args.mock_video:
        raise SystemExit("--mock-video 和 --real-video 不能同时使用")
    if args.real_video:
        return False
    return True


def _resolve_mock_super_resolution(args: argparse.Namespace) -> bool:
    if args.real_super_res and args.mock_super_res:
        raise SystemExit("--mock-super-res 和 --real-super-res 不能同时使用")
    if args.real_super_res:
        return False
    return True


def _resolve_output_dir(project_root: Path, output_dir_arg: str) -> Path:
    output_dir = Path(output_dir_arg)
    if output_dir.is_absolute():
        return output_dir
    return project_root / output_dir


def _parse_parts(parts_text: str) -> list[int]:
    value = parts_text.strip().lower()
    if value == "all":
        return [1, 2, 3, 4, 5, 6]
    if not value:
        raise ValueError("--parts 不能为空，可用值示例：1、1,2、1,2,3、all")

    parts: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if not item.isdigit():
            raise ValueError(f"--parts 包含非法值：{item}，只支持 1-6 或 all")
        part_number = int(item)
        if part_number < 1 or part_number > 6:
            raise ValueError(f"--parts 超出范围：{part_number}，只支持 1-6")
        if part_number not in parts:
            parts.append(part_number)

    return parts


if __name__ == "__main__":
    sys.exit(main())
