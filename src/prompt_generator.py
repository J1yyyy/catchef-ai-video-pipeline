from src.clients.ark_llm_client import ArkLlmClient
from src.models.schemas import LlmConfig


def generate_prompt(filled_prompt: str, llm_config: LlmConfig, mock_llm: bool) -> str:
    if mock_llm:
        return _generate_mock_prompt()

    client = ArkLlmClient(llm_config)
    return client.generate(filled_prompt)


def _generate_mock_prompt() -> str:
    parts = []
    for index in range(1, 7):
        parts.append(
            f"【Part {index}｜15s】\n\n"
            "本段固定角色设定：同一只拟人橘猫，橘色长毛、圆脸、大眼睛、毛茸茸尾巴，穿蓝色牛仔围裙，只用两只后腿直立行走，两只前肢作为手使用，不出现多余肢体。\n"
            "本段场景设定：印尼乡村厨房和院子，泥土地面，木桌，竹篮，温暖自然光。\n"
            "本段食材 / 道具 / 进度状态：随机菜单中的食材被摆在竹篮和木桌上，锅、铲、陶碗准备好。\n"
            "本段声音设定：轻微猫叫、风声、切菜声、锅铲声。\n"
            "可直接复制生成的完整提示词：0s-3s 拟人橘猫走入乡村厨房，3s-7s 整理食材，7s-11s 开始处理菜品，11s-15s 镜头停在温馨的做饭画面，9:16竖屏，无字幕，无人类配音。"
        )
    return "\n\n".join(parts)
