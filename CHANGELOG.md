# Changelog

## v1.7.0

### 新增
- `weblate_create_key`：创建翻译 key（源字符串），自动从组件获取源语言
- `weblate_add_translation`：为已有 key 添加目标语言译文，支持单语言和逗号分隔多语言

### 移除
- `weblate_create_unit`：已由 `weblate_create_key` + `weblate_add_translation` 替代
- `weblate_create_unit_multi`：已由 `weblate_add_translation` 的 `langs` 参数替代

## v1.6.0

### 新增
- `weblate_create_unit_multi`：批量多语言创建翻译单元，一次 tool 调用创建同一 key 的多个语言翻译，减少 LLM tool 往返消耗

## v1.5.3

### 修复
- 模板重载逻辑：插件配置改为唯一数据源，重载时 config 与文件不同则 config 覆盖文件

## v1.5.2

### 修复
- 模板创建/更新/删除后 LLM 收不到结果导致重复创建：改为先 yield 给用户再 yield str 给 LLM

## v1.5.1

### 修复
- 12 个 LLM Tool 参数空值防护：`project_slug`/`component_slug`/`lang` 为空时返回明确提示而非 API 404
- `failing_checks` 修复同上
- CLAUDE.md 新增"防坑指南"章节

## v1.5.0

### 新工具
- `weblate_task_status` — 查看组件后台任务状态（VCS pull/push/commit 结果），yield 直接输出

### SDK
- WTapi 新增 `list_tasks` 方法

## v1.4.0

### 改进
- `weblate_translation_status` 改为直接输出（yield），支持多组件（逗号分隔 / 不填自动列全部）
- `weblate_translation_stats` 改为直接输出（yield），支持多组件 + 多语言
- 翻译进度输出只显示语言名称，不再附带语言代码

## v1.3.0

### 新增
- 项目黑名单：在配置中按行输入 slug 拉黑项目，所有列表和备份自动过滤。支持 `#` 注释
- 配置 slug 提示优化：所有需要 slug 的配置项 hint 都提示"可让 AI 列出获取"

### 修复
- 零宽字符 `We​blate` 清理
- 热重载导致备份循环累积修复

## v1.2.0

### 新工具
- `weblate_backup_now` — 手动触发仓库备份
- `weblate_failing_checks` — 列出检查失败的翻译单元
- `weblate_list_unit_translations` — 查看同 key 在所有语言中的翻译状态

### 改进
- 翻译进度统计 emoji 美化：🟢>80% | 🟡>50% | 🔴<50%，附 📝fuzzy ❌failing 图标
- `weblate_autotranslate` 新增 `filter_type` 参数（all/nontranslated/todo/fuzzy/check）
- 模板系统自动包含"目标项目"参数，`create_unit` 支持 project_slug

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
