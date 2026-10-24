# CatChef AI Video Pipeline

一个本地 Python 工作流：为“橘猫制作印尼菜”生成分镜提示词，按 6 段分别生成视频，并支持任务续跑、画质增强和 FFmpeg 合成。项目提供 mock 模式，可以先体验流程，再自行配置付费 API。

## 工作流程

```text
菜品列表 + 提示词模板
        ↓
大模型生成完整脚本 → 拆分为 6 段提示词
        ↓
Seedance 生成 6 段视频 → state.json 记录任务与续跑状态
        ↓
可选：AI MediaKit 分段超分
        ↓
FFmpeg 本地合成 90 秒视频
```

## 项目实现

- 用独立模块处理配置校验、菜单选择、提示词构建与分段、API 调用、状态管理和视频合成。
- 通过 `state.json` 保存每段任务的 ID、状态和结果；重新运行时可查询已有任务，跳过已完成的真实视频。
- 真实 Seedance 和超分调用分别需要显式指定 `--real-video`、`--real-super-res`，避免 mock 调试时误调用收费接口。
- 提供 Windows 操作菜单，以及命令行方式选择单个或多个 Part。

技术栈：Python 3.10+、火山方舟大模型与 Seedance API、AI MediaKit API、FFmpeg、PyYAML、Requests。

## 橘猫内容展示

这个工作流来自橘猫做菜内容的实际制作：选菜、编写分段提示词、提交视频任务原本需要反复手动操作，因此整理成了可续跑的流程，并提供给非技术同事使用。下图是橘猫项目相关的发布内容截图，展示内容呈现和账号互动；截图数据不单独代表本工具带来的增长。

| 发布内容 | 单条内容互动 |
| --- | --- |
| <img src="assets/showcase/cat-profile.jpg" alt="橘猫做菜内容主页截图" width="280"> | <img src="assets/showcase/cat-post.jpg" alt="橘猫视频互动截图" width="280"> |

## 本地快速体验（不调用付费 API）

环境：Windows PowerShell。以下命令均在仓库根目录执行。

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py --mock-llm --prompt-only
```

预期结果：`outputs/` 下新建一个目录，包含菜单、完整提示词、`part1_prompt.txt` 到 `part6_prompt.txt` 和 `state.json`。这一步不会生成视频。

如果要体验视频任务的状态流转，可运行：

```powershell
.\.venv\Scripts\python.exe main.py --with-video --mock-llm --mock-video --parts 1
```

预期结果：新输出目录中出现 `part1.mp4` 占位文件，`state.json` 将其标记为 mock。占位文件不可播放，也不能作为真实视频参与合成。

真实生成需要自行设置 `ARK_API_KEY`；真实超分另需 `AMK_API_KEY`，并可能产生费用。完整配置、单段验证、续跑和合成命令见 [操作手册](docs/操作手册.md)。

## 目录说明

| 路径 | 作用 |
| --- | --- |
| `main.py` | 命令行入口与流程编排 |
| `src/clients/` | 大模型、Seedance 和 AI MediaKit 客户端 |
| `src/state_manager.py` | 任务状态读写与续跑判断 |
| `src/video_composer.py` | FFmpeg 视频合成 |
| `操作菜单.bat` | Windows 菜单入口 |
| `docs/` | [操作手册](docs/操作手册.md)，包含命令行、Windows 菜单、配置和常见问题 |

运行产生的视频、提示词和任务状态保存在本机 `outputs/`，不会纳入仓库。`assets/orange_cat.png` 是视频生成时使用的角色参考图。
