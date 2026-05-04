# Changelog

## v1.1.0

### 模板系统
- 自然语言模板：AI 根据自然语言描述理解转换规则，自动创建翻译单元
- 三段式模板结构：模板名称、模板内容、所需参数
- AI 辅助创建/更新模板：subagent 独立理解需求生成模板描述
- 模板配置面板：WebUI JSON 编辑器手动编辑，热重载双向同步
- 专有名词保护：模板参数中强制声明"需用户提供英文翻译，禁止 AI 自行翻译"
- LLM 自主 slug 匹配：名称/slug 模糊匹配，AI 自动查表解析

### 新工具
- `weblate_list_languages` — 列出所有语言代码
- `weblate_repository_commit` — 提交仓库变更，补全 pull→commit→push 流程
- `weblate_autotranslate` — 触发批量自动翻译
- `weblate_list_changes` — 全局翻译变更历史
- `weblate_component_lock` — 查看/设置组件锁
- `weblate_translation_stats` — 单个语言精确统计
- `weblate_create_unit_comment` — 添加翻译评论
- `weblate_download_file` — 下载翻译文件并发送给用户
- `weblate_upload_file` — 上传本地翻译文件到 Weblate

### 定时备份
- 小时级快照：可配置间隔和保留数量
- 天级存档：可配置固定时间和保留数量
- 备份配置独立折叠组

## v1.0.0

### 核心工具
- `weblate_list_projects` — 列出所有翻译项目
- `weblate_list_components` — 列出项目组件
- `weblate_translation_status` — 翻译进度统计（含进度条）
- `weblate_translation_changes` — 翻译变更历史
- `weblate_repository_status` — 仓库状态（C/M/P 标记）
- `weblate_repository_pull` — 拉取远程仓库
- `weblate_repository_push` — 推送翻译变更
- `weblate_search_unit` — 搜索翻译单元
- `weblate_translate_unit` — 修改单个翻译
- `weblate_language_stats` — 语言统计

### 基础功能
- LLM Tool 架构：异步调用同步 WTapi（asyncio.to_thread）
- JSON 文件缓存：可配置 TTL，自动过期
- 默认项目配置：一次配置，无需每次指定
- 组件/项目名称→slug 自然语言解析
