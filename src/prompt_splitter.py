import re


class PromptSplitError(ValueError):
    def __init__(self, missing_parts: list[int]):
        self.missing_parts = missing_parts
        missing_text = ", ".join(f"Part {part}" for part in missing_parts)
        super().__init__(f"没有完整识别到 6 个 Part，缺少：{missing_text}")


PART_HEADING_PATTERN = re.compile(r"【Part\s*([1-6])｜15s】")


def split_prompt_parts(prompt_full: str) -> dict[str, str]:
    matches = list(PART_HEADING_PATTERN.finditer(prompt_full))
    found_parts = {int(match.group(1)) for match in matches}
    missing_parts = [part for part in range(1, 7) if part not in found_parts]

    if missing_parts:
        raise PromptSplitError(missing_parts)

    parts: dict[str, str] = {}
    for index, match in enumerate(matches):
        part_number = int(match.group(1))
        if part_number < 1 or part_number > 6:
            continue
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(prompt_full)
        parts[f"part{part_number}"] = prompt_full[start:end].strip() + "\n"

    if len(parts) != 6:
        missing_parts = [part for part in range(1, 7) if f"part{part}" not in parts]
        raise PromptSplitError(missing_parts)

    return parts
