import base64
import os
import time
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    requests = None

from src.models.schemas import SeedanceConfig


class SeedanceClientError(RuntimeError):
    pass


class SeedanceClient:
    SUCCESS_STATUSES = {"succeeded", "success", "completed", "done"}
    RUNNING_STATUSES = {"pending", "queued", "running", "in_progress", "processing"}
    FAILED_STATUSES = {"failed", "error", "cancelled", "canceled", "expired"}

    def __init__(self, config: SeedanceConfig):
        if requests is None:
            raise SeedanceClientError("缺少 requests 依赖，请先执行：pip install -r requirements.txt")

        self.config = config
        api_key = os.getenv(config.api_key_env)
        if not api_key:
            raise SeedanceClientError(
                f"未检测到环境变量 {config.api_key_env}。请先配置火山方舟 API Key，"
                f"例如在 Windows PowerShell 中执行：$env:{config.api_key_env}=\"你的API Key\""
            )

        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self.base_url = config.base_url.rstrip("/")

    def build_reference_image_data_url(self) -> str:
        image_path = self.config.reference_image_path
        if not image_path.exists():
            raise SeedanceClientError(f"参考图不存在：{image_path}")

        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    def create_task(self, prompt: str, reference_image_data_url: str) -> tuple[str, dict[str, Any]]:
        payload = {
            "model": self.config.model,
            "content": [
                {
                    "type": "text",
                    "text": prompt,
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": reference_image_data_url,
                    },
                    "role": self.config.reference_image_role,
                },
            ],
            "ratio": self.config.ratio,
            "resolution": self.config.resolution,
            "duration": self.config.duration,
            "generate_audio": self.config.generate_audio,
            "watermark": self.config.watermark,
        }

        response_data = self._request_json(
            "POST",
            f"{self.base_url}/contents/generations/tasks",
            json=payload,
        )
        task_id = extract_task_id(response_data)
        if not task_id:
            raise SeedanceClientError(f"创建任务成功但未找到 task_id，完整响应：{response_data}")
        return task_id, response_data

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self._request_json(
            "GET",
            f"{self.base_url}/contents/generations/tasks/{task_id}",
        )

    def poll_until_finished(self, task_id: str) -> tuple[str, dict[str, Any]]:
        last_response: dict[str, Any] = {}
        for _ in range(self.config.max_poll_attempts):
            last_response = self.get_task(task_id)
            status = extract_status(last_response)
            if not status:
                raise SeedanceClientError(f"查询任务成功但未找到 status，完整响应：{last_response}")

            normalized_status = status.lower()
            if normalized_status in self.SUCCESS_STATUSES:
                return "done", last_response
            if normalized_status in self.FAILED_STATUSES:
                return normalized_status, last_response
            if normalized_status not in self.RUNNING_STATUSES:
                raise SeedanceClientError(f"未知任务状态：{status}，完整响应：{last_response}")

            time.sleep(self.config.poll_interval_seconds)

        raise SeedanceClientError(
            f"轮询超过最大次数 {self.config.max_poll_attempts}，最后响应：{last_response}"
        )

    def download_video(self, video_url: str, output_path: Path) -> None:
        response = requests.get(
            video_url,
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()
        output_path.write_bytes(response.content)

    def _request_json(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                response = requests.request(
                    method,
                    url,
                    headers=self.headers,
                    timeout=self.config.request_timeout_seconds,
                    **kwargs,
                )
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise SeedanceClientError(f"接口返回不是 JSON 对象：{data}")
                return data
            except Exception as exc:
                last_error = exc
                if attempt < self.config.max_retries:
                    time.sleep(1)

        raise SeedanceClientError(f"Seedance API 请求失败：{last_error}") from last_error


def extract_task_id(response: dict[str, Any]) -> str | None:
    return _first_string(
        response,
        [
            ("id",),
            ("task_id",),
            ("data", "id"),
            ("data", "task_id"),
        ],
    )


def extract_status(response: dict[str, Any]) -> str | None:
    return _first_string(
        response,
        [
            ("status",),
            ("data", "status"),
        ],
    )


def extract_video_url(response: dict[str, Any]) -> str | None:
    return _first_string(
        response,
        [
            ("video_url",),
            ("url",),
            ("content", "video_url"),
            ("content", "download_url"),
            ("result", "video_url"),
            ("result", "download_url"),
            ("data", "video_url"),
            ("data", "result", "video_url"),
            ("data", "result", "download_url"),
        ],
    )


def _first_string(response: dict[str, Any], paths: list[tuple[str, ...]]) -> str | None:
    for path in paths:
        value: Any = response
        for key in path:
            if not isinstance(value, dict) or key not in value:
                value = None
                break
            value = value[key]
        if value:
            return str(value)
    return None
