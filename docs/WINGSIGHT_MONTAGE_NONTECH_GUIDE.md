# 用 wingsight_montage 跑通 wingsight_montage

这份文档面向非技术使用者。目标是让用户在浏览器里用 wingsight_montage 发起视频任务、审批关键选择，并在 `projects/<项目名>/renders/final.mp4` 拿到成片。

## 适合的使用方式

wingsight_montage 不是传统剪辑软件，也不是 wingsight_montage 的独立网页后台。它是 Claude Code / Codex 的浏览器操作界面：用户用自然语言下达任务，Agent 在当前项目目录里读说明、跑命令、生成资产、渲染视频。

推荐把它当作“视频制作助理控制台”：

1. 用户只输入需求和审批选择。
2. Agent 负责选择 pipeline、检查工具、执行生成和渲染。
3. 输出文件固定放在 `projects/<项目名>/renders/`。

## 管理员一次性准备

在项目根目录执行：

```bash
make setup
make preflight
```

当前项目默认优先使用 `.venv/bin/python`。如果项目目录下已经有 `.venv`，依赖会安装进这个虚拟环境。

准备 API key：

1. 复制 `.env.example` 为 `.env`，`make setup` 会自动创建。
2. 零 API key 也能跑基础路径：Remotion/FFmpeg、本地组件、素材检索路径。
3. 想让非技术用户稳定做 AI 图片、TTS、视频生成，建议至少配置：
   - `OPENAI_API_KEY`：TTS / 图片生成备用。
   - `FAL_KEY`：FLUX 图片、Kling/Veo/MiniMax 等视频网关。
   - `PEXELS_API_KEY` 或 `PIXABAY_API_KEY`：免费素材检索。
   - `ELEVENLABS_API_KEY`：高质量配音、音效、音乐。

## wingsight_montage 启动方式

本机已经安装 Bun，并在 `apps/companion` 使用项目内 The Companion 源码。浏览器打开：

```text
http://localhost:3456
```

给非技术用户使用时，管理员先运行：

```bash
scripts/open-user-session.sh
```

这个脚本每运行一次，默认创建一个新的独立视频任务会话。它会自动：

1. 启动项目内 `apps/companion` 源码版 Companion；
2. 创建当前项目的新会话；
3. 使用 Codex backend；
4. 固定工作目录为 `/home/shenglin/Desktop/wingsight_Montage`；
5. 把会话命名为“wingsight_montage 视频助手 + 时间戳”。

运行后会输出一个链接，形如：

```text
http://localhost:3456/#/session/<session-id>
```

把这个链接给用户即可。用户只需要打开链接并输入视频需求。

浏览器里的 `New Session` 也已经被改成非技术用户模式：点击后会直接创建当前项目的新会话，不会要求用户选择路径、模型、权限或 backend。

如果管理员想回到已有会话，而不是创建新任务，可以运行：

```bash
scripts/open-user-session.sh --reuse
```

如果服务没有启动，在项目根目录执行：

```bash
scripts/start-wingsight_montage.sh start
```

如果页面看不到最新 UI，先确认没有旧的全局 Companion 服务占用端口：

```bash
systemctl --user status the-companion.service
scripts/start-wingsight_montage.sh status
```

当前推荐只使用项目脚本管理服务，不再使用全局 `the-companion.service`。

查看状态：

```bash
scripts/start-wingsight_montage.sh status
```

停止服务：

```bash
scripts/start-wingsight_montage.sh stop
```

也可以前台启动，方便看日志：

```bash
scripts/start-wingsight_montage.sh
```

The Companion 页面已经做了轻量用户模式处理：

- 左侧只显示当前项目的历史会话。
- `New Session` 保留，但自动使用当前项目配置。
- 右侧 Context 顶部有 `Files` 文件树。
- 隐藏 Prompts、Integrations、Environments、Sandboxes、Agents、Settings、Diffs、GitHub PR、Linear Issue、MCP Servers、Git Branch、Usage Limits 等技术入口。
- 隐藏会话卡片里的本机路径和 backend 标记。

非技术用户不要切换目录，也不要编辑 `pipeline_defs/`、`skills/`、`tools/`。

## 上传参考图和参考视频

建议不要依赖输入框里的附件。某些 wingsight_montage / Codex 版本里，Agent 能看到“有附件”，但拿不到附件在磁盘上的真实路径，最后会要求用户提供文件路径。

推荐统一使用右侧 Context 里的 `Files`。管理员通过 `scripts/start-wingsight_montage.sh` 启动服务时，会自动给 The Companion 注入这个轻量文件面板：

1. 点 `Files` 右上角的上传按钮 `+`。
2. 把图片、视频、音频上传到 `projects/uploads/`。
3. 在文件树里选择一个或多个文件。
4. 点 `@` 把选中文件插入输入框，点复制按钮复制路径，或点下载按钮下载文件。
5. 用普通话描述用途。

多文件任务可以多选后一键 `@`：

```text
把 @projects/uploads/source.png 做成 @projects/uploads/style.png 的风格。
```

参考视频分析建议这样写：

```text
请先分析 @projects/uploads/reference.mp4 的节奏、镜头、字幕和转场，不要直接生成。
```

这个流程对非技术用户更稳定：用户不用理解系统路径，Agent 也能直接读取项目目录下的文件。

## 给非技术用户的固定开场提示词

现在不再自动把内部规则发进聊天记录。用户可以直接写自然语言需求，例如：

```text
做一个 45 秒中文短视频，主题是“为什么天空是蓝色的”，发抖音，适合中学生，轻松但专业，需要旁白和字幕。
```

示例：

```text
请用 wingsight_montage 帮我制作一个视频。

先不要直接生成。请先：
1. 按 AGENT_GUIDE.md 选择合适的 pipeline；
2. 做工具能力 preflight；
3. 用普通人能理解的话告诉我可用能力、预计成本、需要我选择的方案；
4. 等我确认后再开始生成。

我的视频需求是：
做一个 45 秒中文短视频，主题是“为什么天空是蓝色的”，发抖音，适合中学生，轻松但专业，需要旁白和字幕。
```

## 用户审批时只看这三件事

Agent 给出方案后，非技术用户只需要确认：

1. 视频方向：主题、风格、时长是否对。
2. 成本路径：免费路径、低成本路径还是高质量付费路径。
3. 渲染方式：如果 Agent 提供 Remotion 和 HyperFrames 两个选项，按推荐项确认即可。

推荐回复格式：

```text
确认。使用你推荐的方案，预算上限 X 美元。开始生成。
```

## 常用任务模板

短视频科普：

```text
做一个 60 秒中文科普短视频，主题是 [主题]，平台是抖音/视频号，面向 [人群]，需要旁白、字幕、轻快配乐。
```

产品宣传：

```text
做一个 45 秒产品介绍视频，产品是 [产品名]，核心卖点是 [卖点]，风格干净专业，适合官网和朋友圈转发。
```

参考视频复刻风格：

```text
这是我喜欢的参考视频：[链接]。请分析它的节奏、结构和视觉风格，然后做一个同节奏但不同内容的视频，主题是 [主题]。
```

真实素材混剪：

```text
做一个 75 秒纪录片感混剪，主题是 [主题]，使用真实 footage only，不要 AI 生成画面，需要音乐，可以不要旁白。
```

## 成片在哪里

默认输出位置：

```text
projects/<项目名>/renders/final.mp4
```

中间资产通常在：

```text
projects/<项目名>/assets/
projects/<项目名>/artifacts/
```

如果需要发给别人，只拿 `renders/final.mp4`。

## 出问题时怎么让用户反馈

让用户直接把 wingsight_montage 里的报错复制给 Agent，并说：

```text
请解释这个错误属于依赖、权限、API key、额度、素材质量还是渲染问题。先给我推荐修复方案，不要自行切换大模型或付费供应商。
```

## 管理建议

建议给非技术用户预置 3 个固定入口：

1. “科普短视频”
2. “产品宣传片”
3. “参考视频改编”

每个入口只让用户填主题、目标平台、时长、风格、预算上限。其他选择交给 Agent 提案和审批。
