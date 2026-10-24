from pathlib import Path


class PromptTemplateError(ValueError):
    pass


MENU_PLACEHOLDER = "{{MENU}}"


def build_prompt(prompt_template_path: Path, menu: list[str]) -> str:
    if not prompt_template_path.exists():
        raise PromptTemplateError(f"提示词模板不存在：{prompt_template_path}")

    template = prompt_template_path.read_text(encoding="utf-8")
    if MENU_PLACEHOLDER not in template:
        raise PromptTemplateError(f"提示词模板缺少菜单占位符：{MENU_PLACEHOLDER}")

    menu_text = "\n".join(f"- {dish}" for dish in menu)
    return template.replace(MENU_PLACEHOLDER, menu_text)
