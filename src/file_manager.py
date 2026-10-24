import re
from datetime import datetime
from pathlib import Path


def create_output_dir(output_root: Path, menu: list[str]) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    date_text = datetime.now().strftime("%Y-%m-%d")
    dish_slugs = [_slugify(dish) for dish in menu]
    slug_text = "_".join(dish_slugs)
    base_name = _truncate_folder_name(f"{date_text}_{slug_text}")
    candidate = output_root / base_name

    if not candidate.exists():
        candidate.mkdir(parents=True)
        return candidate

    for index in range(2, 100):
        suffix = f"_{index:02d}"
        truncated_base = _truncate_folder_name(base_name, reserved_length=len(suffix))
        candidate = output_root / f"{truncated_base}{suffix}"
        if not candidate.exists():
            candidate.mkdir(parents=True)
            return candidate

    raise RuntimeError(f"输出目录重名过多，无法创建新目录：{output_root / base_name}")


def save_menu(output_dir: Path, menu: list[str]) -> Path:
    content = "\n".join(menu) + "\n"
    return save_text(output_dir / "menu.txt", content)


def save_filled_prompt(output_dir: Path, filled_prompt: str) -> Path:
    return save_text(output_dir / "filled_prompt.txt", filled_prompt)


def save_prompt_full(output_dir: Path, prompt_full: str) -> Path:
    return save_text(output_dir / "prompt_full.txt", prompt_full)


def save_prompt_raw_failed(output_dir: Path, prompt_full: str) -> Path:
    return save_text(output_dir / "prompt_raw_failed.txt", prompt_full)


def save_part_prompts(output_dir: Path, parts: dict[str, str]) -> list[Path]:
    saved_paths = []
    for part_number in range(1, 7):
        key = f"part{part_number}"
        saved_paths.append(save_text(output_dir / f"{key}_prompt.txt", parts[key]))
    return saved_paths


def save_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _slugify(value: str) -> str:
    slug = _remove_parentheses_content(value.strip())
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r'[\\/:*?"<>|]', "", slug)
    slug = re.sub(r"[()（）]", "", slug)
    slug = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff_-]", "", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = re.sub(r"_+", "_", slug)
    slug = slug.strip("_-")
    if not slug:
        slug = "dish"
    return slug[:32].strip("_-") or "dish"


def _remove_parentheses_content(value: str) -> str:
    value = re.sub(r"（[^（）]*）", "", value)
    value = re.sub(r"\([^()]*\)", "", value)
    return value


def _truncate_folder_name(name: str, reserved_length: int = 0) -> str:
    max_length = 120 - reserved_length
    if len(name) <= max_length:
        return name
    return name[:max_length].rstrip("_-")
