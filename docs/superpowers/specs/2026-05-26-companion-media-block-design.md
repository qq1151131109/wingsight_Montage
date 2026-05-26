# 2026-05-26 Companion 媒体内容块设计

## 背景

当前项目中的 The Companion 前端已经具备会话、权限、Claude/Codex 兼容和基础文件预览能力，但对导演最关键的“在聊天流里直接看到并讨论素材”支持不足。现状更接近文本优先的 agent 聊天界面，用户经常需要跳去目录树或文件面板才能查看图片、视频和文档，这会打断导演围绕素材做创作决策的工作流。

用户已经明确：

- 长期希望产品体验接近 Lovart，简单、灵活、media-first。
- 短期以快速上线为主，不做大规模前端重构。
- assistant 单条回复中应能包含多个正式内容块。
- 首版只覆盖 agent 明确产出的本地文件。
- 图片直接展示；视频和文档在站内快速预览，不跳出应用。
- 首版只做展示 + 点击预览，不做批注、版本对比或拖拽回引用。
- 前后端统一放在一个 monorepo 中管理，但保持清晰目录边界。

## 目标

短期版本的目标不是重做整个导演工作台，而是在现有 Companion 结构上，把 agent 回复从“纯文本 + 工具轨迹”升级为“可直接承载素材的内容流”。

交付后，导演在一条 assistant 回复中应能：

- 直接看到生成的图片。
- 看到生成的视频和文档对应的正式 block。
- 点击视频 / 文档 block 后，在站内现有预览区域快速查看内容。
- 不再依赖先去目录树中找文件，再回到聊天上下文理解它们与回复的关系。

## 非目标

本次设计不包含以下内容：

- 不把 Companion 重构成 ArcReel 式三栏工作台。
- 不引入多用户协作能力。
- 不支持外部 URL、云文档或第三方文件系统预览。
- 不做从自然语言中模糊识别路径。
- 不做用户手动附加任意项目文件到 assistant 回复。
- 不做批注、评论、对比、多选编排、版本回滚入口。
- 不做新的独立媒体预览系统。

## 方案总览

采用正式协议扩展方案：直接在现有 `ContentBlock` 体系上新增 `image`、`video`、`document` 三种一等 block 类型，并允许这些 block 出现在 assistant 单条回复的 `contentBlocks` 中。

这不是临时映射层，也不是纯前端猜测，而是消息协议的正式扩展。媒体 block 由后端在 assistant 消息归一化阶段显式生成，前端只负责按 block 类型渲染和响应点击。

## 仓库组织

前后端统一保留在同一个 monorepo 中管理。

推荐组织方式保持现状边界：

- 前端继续位于 `apps/companion/web/src/`
- 后端继续位于 `apps/companion/web/server/`
- 共享协议类型继续从 server 类型导出到前端使用

这样做的原因是，这次改动跨越了一整条链路：

1. agent 产出文件
2. 后端识别并归一化为 block
3. 前端在消息流中渲染
4. 点击后联动现有文件预览能力

如果拆成多仓，会增加协议版本同步、联调和回滚成本；对当前阶段不划算。

## 数据模型设计

现有 `ContentBlock` 包含：

- `text`
- `tool_use`
- `tool_result`
- `thinking`

首版新增以下三类 block：

### image block

```ts
{
  type: "image";
  path: string;
  title?: string;
  mimeType?: string;
  source: "agent_output";
}
```

### video block

```ts
{
  type: "video";
  path: string;
  title?: string;
  mimeType?: string;
  posterPath?: string;
  durationSec?: number;
  source: "agent_output";
}
```

### document block

```ts
{
  type: "document";
  path: string;
  title?: string;
  docKind: "markdown" | "text" | "json" | "pdf" | "word" | "spreadsheet";
  mimeType?: string;
  excerpt?: string;
  source: "agent_output";
}
```

### 设计原则

- `path` 是主键级信息，所有预览最终都基于本地文件路径。
- `title` 是展示友好信息，不作为查找依据。
- `source` 首版固定为 `agent_output`，避免过早泛化到用户上传、外部文档或手工引用。
- `document.docKind` 只覆盖首版明确支持的文档类型，避免做一个泛化但无行为差异的 document 类型。

## assistant 回复结构

assistant 单条回复可按顺序混排多种 block。例如：

1. `text`
2. `image`
3. `text`
4. `video`
5. `document`

这意味着素材不是“附件列表”，而是和文本说明并列的正式内容块。顺序必须保留，以确保导演在阅读时能理解“这段说明对应哪张图、哪个视频、哪个文档”。

## block 来源与后端职责

首版只覆盖 **agent 明确产出的本地文件**。

后端在 assistant 消息归一化阶段生成媒体 block，识别来源仅限以下明确线索：

1. 工具结果中明确返回的产出文件路径。
2. 系统事件 / 任务通知中明确给出的输出文件路径。
3. 后端自己已经掌握并确认属于当前 assistant 汇报内容的保存路径。

首版明确排除：

- 从自然语言文本中扫描和猜测路径。
- 基于模糊关键词把旧文件挂到当前回复。
- 只要 assistant 文本里出现了像路径的字符串就自动生成 block。

后端职责：

- 判断文件类型。
- 决定生成 `image / video / document` 哪一类 block。
- 为 `document` 推断 `docKind`。
- 在有能力时补充 `title / excerpt / durationSec / posterPath` 等元信息。
- 将这些 block 写入最终 assistant 消息的 `contentBlocks`。

前端不承担任何“猜它是不是文件”的责任。

## 前端渲染设计

### 渲染入口

前端继续以 assistant message 的 `contentBlocks` 为单一渲染入口，在现有 assistant message block renderer 体系上扩展三类 block renderer。

不引入第二套媒体消息流，不新增“附件专用 renderer 体系”。

### image block

表现：

- 直接在消息流中内联显示。
- 单张图按正文宽度约束展示。
- 多张图按回复顺序垂直排列；首版不做复杂画廊布局。
- 点击可放大查看。

首版中，图片不强制联动右下角预览；重点是让它在消息里“立刻可见”。

### video block

表现：

- 在消息流中显示为正式视频 block。
- block 至少包含：缩略区域、文件名或标题、时长（若有）、“预览”动作提示。
- 点击后切换站内现有文件预览区域到对应视频文件，由已有 `video` 预览逻辑播放。

视频首版不在消息流中直接自动播放，以降低布局和性能复杂度。

### document block

表现：

- 在消息流中显示为正式文档 block。
- block 至少包含：标题、文档类型标签、简短摘要（若有）。
- 点击后切换站内现有文件预览区域到对应文档文件。

文档类型处理：

- `markdown / text / json`：优先使用现有文本或 markdown 渲染路径。
- `pdf`：使用现有 iframe/raw blob 预览路径。
- `word / spreadsheet`：使用现有 `/fs/preview` + office 预览路径。

## 站内预览复用策略

不新造第二套预览系统。

现有文件预览已经覆盖：

- 图片
- 视频
- 音频
- PDF
- Word
- Spreadsheet
- Markdown
- 普通文本 / 代码

因此本设计的职责分离如下：

- **聊天 block**：让素材出现在对话上下文里。
- **右下角文件预览**：让用户在站内细看素材。

点击 `video` / `document` block 时，不打开新标签页，不弹出另一套复杂 modal，而是触发一个共享的“open preview for path”行为，把现有文件预览切到对应路径。

## 预览状态共享设计

当前 `FilesPanel` 的 `selectedFilePath` 是组件内部局部状态，这不适合从聊天 block 直接驱动。

因此首版需要把“当前预览文件路径”提升为 session 级共享 UI 状态。推荐做法：

- 在 UI store 中新增类似 `previewSelectedFileBySession` 的状态映射。
- 新增 `setPreviewSelectedFile(sessionId, filePath | null)` action。
- `FilesPanel` 改为优先读取该共享状态，并在用户在文件树中手动点击文件时同步更新它。
- 聊天 block 点击时只调用这个共享 action，而不直接操作 `FilesPanel` 内部状态。

这样可以保证：

- 文件树选择和聊天 block 点击操作落到同一个状态源。
- 预览行为一致。
- 后续如果要从别的地方（如任务面板、diff 面板、素材托盘）打开预览，也能复用同一个入口。

## 兼容与边界

### 首版覆盖范围

仅覆盖以下来源：

- 当前 session 中 agent 明确产出的本地文件。

不覆盖：

- 用户历史目录中的任意现有文件。
- assistant 文本中仅被提到但未作为明确产出上报的路径。
- 云文档、外部链接、网络资源。

### 降级规则

- 文件存在但类型无法识别：降级为 `document` block。
- 文件不存在或无权限读取：不渲染正常媒体 block；统一降级为普通文本说明，避免首版再引入第四种错误态媒体 block。
- 预览能力不可用：block 仍可显示，但点击后应给出明确提示，必要时提供下载动作。
- 文件虽然存在，但不属于当前 session 明确产出链路：首版不挂载 block，避免跨会话或历史文件误关联。

## 交互细节

### 首版保留的交互

- 图片 block：可见、点击放大。
- 视频 block：点击在站内预览。
- 文档 block：点击在站内预览。

### 首版不做的交互

- 评论 / 批注
- block 排序拖拽
- 多 block 对比
- 从 block 一键回填到输入框
- block 的版本切换
- block 的批量操作

## 测试策略

### 类型与协议测试

- `ContentBlock` 新 union 类型的类型检查。
- assistant message 历史回放与实时流合并时能正确保留新 block。
- Claude / Codex 两条链路都能接受和传递新 block 类型。

### 前端组件测试

- assistant message 可渲染 `image / video / document` block。
- 图片 block 直接可见。
- 视频 / 文档 block 点击后触发共享预览状态更新。
- 文件不存在、类型不识别、预览失败时有明确 fallback。

### 预览联动测试

- 视频 block 点击后，现有文件预览正确播放视频。
- PDF block 点击后，现有文件预览正确显示 PDF。
- Word / Spreadsheet block 点击后，现有 office 预览路径被正确调用。
- Markdown / text / json 文档 block 点击后，现有文本预览路径被正确调用。

### 手动验证

至少覆盖以下路径：

1. agent 产出图片 → assistant 回复中直接看到图片。
2. agent 产出多个图片 → 同一回复中顺序显示多个 image block。
3. agent 产出视频 → assistant 回复中出现 video block，点击后右下角可播。
4. agent 产出 markdown / json → assistant 回复中出现 document block，点击后右下角可看。
5. agent 产出 pdf / docx / xlsx → document block 点击后复用现有站内预览。
6. 一条 assistant 回复同时包含文本 + 多个 block，阅读顺序正确。

## 风险与控制

### 风险 1：后端 block 识别标准过于隐式

控制方式：

- 首版严格限定只认明确产出文件。
- 不从自然语言里做推断。
- block 生成逻辑集中在消息归一化层，避免多处分散判断。

### 风险 2：聊天与文件预览出现双状态源

控制方式：

- 将文件预览选中文件提升到 store，作为唯一状态源。
- 文件树和聊天 block 都只通过同一 action 改变预览目标。

### 风险 3：首版 block 太重，影响消息流稳定性

控制方式：

- 图片只做简单内联，不做复杂 gallery。
- 视频不做消息流内直接播放。
- 文档不内联全文，只提供 block + 现有预览联动。

## 推荐实施顺序

1. 扩展 `ContentBlock` 协议类型。
2. 扩展后端 assistant 消息归一化，生成三类 block。
3. 在 store 中引入共享预览文件状态。
4. 让 `FilesPanel` 使用共享预览状态。
5. 扩展 assistant block renderer，新增 `image / video / document` renderer。
6. 接入点击 block → 打开右下角预览。
7. 补测试与 playground 场景。

## 结论

短期版本不更换 Companion，不做大规模布局重构，而是在现有 block 消息体系上正式引入 `image / video / document` 三种一等内容块。assistant 单条回复可以顺序混排文本与媒体 block；图片直接内联显示，视频和文档点击后复用现有右下角站内预览。

这是一个既符合当前快速上线目标、又与长期 Lovart 式 media-first 方向一致的演进方案。
