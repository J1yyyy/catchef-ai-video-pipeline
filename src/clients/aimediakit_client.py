import os
import time
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    requests = None

from src.models.schemas import SuperResolutionConfig


class AIMediaKitClientError(RuntimeError):
    pass


class AIMediaKitClient:
    SUCCESS_STATUSES = {"succeeded", "success", "completed", "done"}
    RUNNING_STATUSES = {"pending", "queued", "running", "in_progress", "processing"}
    FAILED_STATUSES = {"failed", "error", "cancelled", "canceled", "expired"}

    def __init__(self, config: SuperResolutionConfig):
        if requests is None:
            raise AIMediaKitClientError("缺少 requests 依赖，请先执行：pip install -r requirements.txt")

        self.config = config
        api_key = os.getenv(config.api_key_env)
        if not api_key:
            raise AIMediaKitClientError(
                f"未检测到环境变量 {config.api_key_env}。请先配置 AI MediaKit API Key，"
                f"例如在 Windows PowerShell 中执行：$env:{config.api_key_env}=\"你的API Key\""
            )

        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self.base_url = config.base_url.rstrip("/")

    def create_enhance_task(self, source_video_url: str) -> tuple[str, dict[str, Any]]:
        payload = self._build_enhance_payload(source_video_url)
        response_data = self._request_json(
            "POST",
            self._join_url(self.config.submit_path),
            json=payload,
        )
        task_id = extract_task_id(response_data)
        if not task_id:
            raise AIMediaKitClientError(f"创建超分任务成功但未找到 task_id，完整响应：{response_data}")
        return task_id, response_data

    def get_task(self, task_id: str) -> dict[str, Any]:
        query_path = self.config.query_path_template.format(task_id=task_id)
        return self._request_json("GET", self._join_url(query_path))

    def poll_until_finished(self, task_id: str) -> tuple[str, dict[str, Any]]:
        last_response: dict[str, Any] = {}
        for _ in range(self.config.max_poll_attempts):
            last_response = self.get_task(task_id)
            status = extract_status(last_response)
            if not status:
                raise AIMediaKitClientError(f"查询超分任务成功但未找到 status，完整响应：{last_response}")

            normalized_status = status.lower()
            if normalized_status in self.SUCCESS_STATUSES:
                return "done", last_response
            if normalized_status in self.FAILED_STATUSES:
                return normalized_status, last_response
            if normalized_status not in self.RUNNING_STATUSES:
                raise AIMediaKitClientError(f"未知超分任务状态：{status}，完整响应：{last_response}")

            time.sleep(self.config.poll_interval_seconds)

        raise AIMediaKitClientError(
            f"轮询超过最大次数 {self.config.max_poll_attempts}，最后响应：{last_response}"
        )

    def download_video(self, video_url: str, output_path: Path) -> None:
        response = requests.get(
            video_url,
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()
        output_path.write_bytes(response.content)

    def _build_enhance_payload(self, source_video_url: str) -> dict[str, Any]:
        # AI MediaKit API Explorer 如有字段变动，只需要调整这个映射函数。
        return {
            "video_url": source_video_url,
            "task_type": self.config.task_type,
            "target_resolution": self.config.target_resolution,
        }

    def _join_url(self, path: str) -> str:
        normalized_path = path if path.startswith("/") else f"/{path}"
        return f"{self.base_url}{normalized_path}"

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
                    raise AIMediaKitClientError(f"接口返回不是 JSON 对象：{data}")
                return data
            except Exception as exc:
                last_error = exc
                if attempt < self.config.max_retries:
                    time.sleep(1)

        raise AIMediaKitClientError(f"AI MediaKit API 请求失败：{last_error}") from last_error


def extract_task_id(response: dict[str, Any]) -> str | None:
    return _first_string(
        response,
        [
            ("task_id",),
            ("id",),
            ("data", "task_id"),
            ("data", "id"),
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


def extract_output_video_url(response: dict[str, Any]) -> str | None:
    return _first_string(
        response,
        [
            ("video_url",),
            ("output_url",),
            ("download_url",),
            ("result", "video_url"),
            ("result", "output_url"),
            ("data", "video_url"),
            ("data", "output_url"),
            ("data", "download_url"),
            ("data", "result", "video_url"),
            ("data", "result", "output_url"),
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
