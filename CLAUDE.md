# WTBot — AstrBot Weblate 翻译管理插件

## 项目概述

WTBot 是 AstrBot 框架的插件，通过 LLM Tool 机制让用户用自然语言管理 Weblate 翻译项目。v1.3.1，28 个 LLM Tool + 模板系统 + 定时备份 + 黑名单过滤。

## 项目结构

```
WTBot/
├── main.py              # 核心：Star 子类 + 全部 LLM Tool（~1200 行）
├── wtapi/               # 内嵌的 Weblate SDK（148 方法，仅依赖 requests）
├── metadata.yaml        # AstrBot 插件元数据（name/desc/version）
├── _conf_schema.json    # 插件配置 Schema（WebUI 面板）
├── requirements.txt     # requests>=2.28
├── CHANGELOG.md
├── CLAUDE.md
└── LICENSE
```

## 部署

- 开发仓库：`~/Documents/Code/WTBot/`（GitHub: `heerxingen/astrbot_plugin_wtbot`）
- AstrBot 安装：`~/Astrbot/`（通过 `uv` 运行）
- 插件目录：`~/Astrbot/data/plugins/astrbot_plugin_wtbot/`
- 数据目录（缓存/备份/模板）：`~/Astrbot/data/plugin_data/wtbot/`
- `main.py` 中通过 `sys.path.insert(0, __file__ dirname)` 让 wtapi 可导入

### ⚠️ 修改后必须同步到插件目录
每次修改 main.py、_conf_schema.json、metadata.yaml、requirements.txt 后，必须同步：
```bash
cp ~/Documents/Code/WTBot/main.py ~/Astrbot/data/plugins/astrbot_plugin_wtbot/main.py
cp ~/Documents/Code/WTBot/_conf_schema.json ~/Astrbot/data/plugins/astrbot_plugin_wtbot/_conf_schema.json
cp ~/Documents/Code/WTBot/metadata.yaml ~/Astrbot/data/plugins/astrbot_plugin_wtbot/metadata.yaml
```
其他文件（CHANGELOG、LICENSE、CLAUDE.md 等）也一并同步对应路径。
修改 wtapi/ 目录时同样需同步到插件目录下的 wtapi/。

## 核心架构

### 类结构
- `WTBot(Star)` — 插件主类
- 所有工具方法在类内，无外部模块拆分
- `__init__` 接收 `Context` + `AstrBotConfig`，调用 `super().__init__(context)`
- 后台任务 `_backup_loop()` 在 `__init__` 中通过 `asyncio.get_running_loop().create_task()` 启动

### LLM Tool 两种返回模式
- **`return str`** — LLM 可 chain 调用。用于查询类工具（list/show/search/stats）
- **`yield event.plain_result(...)`** + 返回 `MessageEventResult` — 直接输出给用户，不经过 LLM。用于创建/修改/删除操作和手动备份

### 同步→异步桥接
WTapi 基于 `requests`（同步），所有调用通过 `asyncio.to_thread()` 扔线程池：
```python
result = await asyncio.to_thread(self.wt.some_method, arg1, arg2)
```

### 缓存
- JSON 文件缓存：`data/plugin_data/wtbot/cache/{key}.json`
- 方法：`_cache_get(key)`, `_cache_set(key, payload)`, `_cache_clear_prefix(prefix)`
- TTL 由配置 `cache_ttl` 控制

### 模板系统
- 模板文件：`data/plugin_data/wtbot/templates.json`
- 三段式：`name` + `description`（自然语言）+ `params`（参数列表，含"目标项目"和"目标组件"）
- 配置文件 `templates_override` 提供 JSON 编辑器（`editor_mode: true`）
- 双向同步：LLM 写文件 → 自动写 config；用户改 config → 热重载检测导入文件
- Subagent：`_tpl_call_ai` 用独立 prompt 调 AI，不受用户人格影响

### 备份系统
- 后台循环每分钟检查，执行小时级和天级备份
- 配置在 `backup` 嵌套对象中
- 备份文件：`data/plugin_data/wtbot/backups/{hourly|daily|manual}/{slug}_{timestamp}.zip`

### 项目黑名单
- 配置 `project_blacklist`：text 类型，每行一个 slug，`#` 注释
- `_blacklist` 属性解析 → `set[str]`
- `list_projects` 和 `_do_backup` 中自动过滤

### Slug 解析
- 所有 `project_slug` 参数默认 `""` → `_resolve_project()` 回退配置 `default_project`
- Tool 描述中告知 LLM："若用户用名称而非 slug，先调 list_xxx 查表匹配"

### 防止热重载副作用
- 备份循环用类级别 `_backup_started = False` 标记，`__init__` 中仅首次启动
- 防止每次 `save_config()` 触发热重载后创建重复循环

## 常用开发模式

### 新增 LLM Tool
1. `grep "def <method>" wtapi/client.py` 确认 WTapi 有对应方法
2. 在 main.py 加 `@filter.llm_tool(name="weblate_xxx")` 装饰的 async 方法
3. 查询类 `return str`，创建/修改/删除类 `yield event.plain_result(...)` + 返回类型 `MessageEventResult`
4. 参数有 project_slug 的加 `= ""` 默认，函数体内调 `project_slug = self._resolve_project(project_slug)`
5. slug 参数的 Args 描述：`项目 slug（非名称）。若用户用名称，先调 weblate_list_projects 获取列表从中匹配`

### 新增配置项
编辑 `_conf_schema.json`，字段格式：
```json
"key_name": {
    "description": "中文说明",
    "type": "string|bool|int|object|text",
    "hint": "悬浮提示文字",
    "default": <默认值>
}
```
- `type: "object"` + `items` → WebUI 折叠组
- `_special: "select_provider"` → 下拉选 AI 模型
- `"editor_mode": true` + `"editor_language": "json"` → 代码编辑器
- AstrBot 保存配置后自动热重载

### 提交前检查
```bash
# 格式化 + lint（AstrBot 规范要求）
ruff format main.py
ruff check main.py
# 编译检查
python3 -m py_compile main.py
```

## 版本管理

### 版本号规则（严格）
- **加新功能** → 第二位 +1（`v1.2.0` → `v1.3.0`）
- **修 bug** → 第三位 +1（`v1.2.0` → `v1.2.1`）
- **第一位（主版本）** → 未经用户明确允许，禁止修改
- ⚠️ 改版本号必须同步三处：`metadata.yaml` version + `CHANGELOG.md` 新条目置顶 + commit message 含版本号

### 提交示例
```bash
# 新功能
vim metadata.yaml  # version: 1.2.0 → 1.3.0
vim CHANGELOG.md   # 新增 v1.3.0 条目
git add -A && git commit -m "v1.3.0: 新功能描述"

# 修 bug
vim metadata.yaml  # version: 1.2.0 → 1.2.1
vim CHANGELOG.md   # 新增 v1.2.1 条目
git add -A && git commit -m "v1.2.1: 修复描述"
```

## Git 约定
- 推送默认后台，卡了不管
- 两个远程：`heerxingen/WTapi`（SDK）和 `heerxingen/astrbot_plugin_wtbot`（插件）

## WTapi SDK 位置
`~/Documents/Code/WTapi/`（GitHub: `heerxingen/WTapi`），与 WTBot 同级。
