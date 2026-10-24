import os

from src.models.schemas import LlmConfig


class ArkLlmClientError(RuntimeError):
    pass


class ArkLlmClient:
    def __init__(self, config: LlmConfig):
        self.config = config
        api_key = os.getenv(config.api_key_env)
        if not api_key:
            raise ArkLlmClientError(
                f"未检测到环境变量 {config.api_key_env}。请先配置火山方舟 API Key，"
                f"例如在 Windows PowerShell 中执行：$env:{config.api_key_env}=\"你的API Key\""
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ArkLlmClientError("缺少 openai 依赖，请先执行：pip install -r requirements.txt") from exc

        self.client = OpenAI(
            api_key=api_key,
            base_url=config.base_url,
        )

    def generate(self, prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                temperature=self.config.temperature,
                max_completion_tokens=self.config.max_completion_tokens,
            )
        except Exception as exc:
            raise ArkLlmClientError(f"火山方舟大语言模型 API 调用失败：{exc}") from exc

        content = response.choices[0].message.content
        if not content:
            raise ArkLlmClientError("火山方舟大语言模型 API 返回内容为空")

        return content
