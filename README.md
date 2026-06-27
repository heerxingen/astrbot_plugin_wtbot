# 石墩子

![Stone Badge](https://stone.professorlee.work/api/stone/heerxingen/astrbot_plugin_wtbot)

# WTBot — AstrBot Weblate 翻译管理插件

通过 LLM Tool 机制让用户用自然语言管理 Weblate 翻译项目。AstrBot 框架插件。

## 功能

- **翻译管理** — 查看进度、搜索翻译、修改翻译单元
- **仓库操作** — pull/push/commit VCS 仓库，查看后台任务状态
- **批量自动化** — 自动翻译、批量创建翻译单元
- **质量检查** — 列出检查失败的翻译条目
- **文件传输** — 下载/上传翻译文件
- **模板系统** — 自然语言模板，AI 根据描述自动创建翻译
- **定时备份** — 小时/天级 ZIP 备份
- **项目黑名单** — 按 slug 过滤项目

## 安装

```bash
# 安装到 AstrBot 插件目录
git clone https://github.com/heerxingen/astrbot_plugin_wtbot.git \
  ~/Astrbot/data/plugins/astrbot_plugin_wtbot/

# 安装依赖
pip install requests>=2.28
```

## 配置

在 AstrBot WebUI 插件面板中配置：

| 配置项 | 说明 |
|---|---|
| `weblate_url` | Weblate 实例地址 |
| `weblate_token` | API Token（在 Weblate 个人设置中生成） |
| `default_project` | 默认项目 slug |
| `default_lang` | 默认语言代码 |
| `cache_ttl` | 缓存过期时间（秒） |
| `project_blacklist` | 项目黑名单，每行一个 slug |
| `templates_override` | 模板 JSON 编辑器 |
| `backup.*` | 备份配置（间隔、保留数量） |

## 使用

在聊天中直接向 Bot 提问，LLM 自动调度对应工具：

```
查看项目列表
hello 项目的翻译进度
搜索 "Cancel" 的日文翻译
拉取 android 组件的远程仓库
```

提供 29 个 LLM Tool，覆盖翻译管理全流程。

## 项目结构

```
WTBot/
├── main.py              # 插件核心：所有 LLM Tool
├── wtapi/               # 内嵌 Weblate SDK（基于 requests）
├── metadata.yaml        # AstrBot 插件元数据
├── _conf_schema.json    # 插件配置 Schema
├── requirements.txt     # 依赖
├── CHANGELOG.md         # 版本变更记录
├── CLAUDE.md            # AI 开发文档
└── LICENSE
```

## 开发

```bash
# 格式化 + 检查
ruff format main.py
ruff check main.py

# 编译检查
python3 -m py_compile main.py

# 同步到插件目录
cp main.py metadata.yaml _conf_schema.json requirements.txt \
   ~/Astrbot/data/plugins/astrbot_plugin_wtbot/
```

配套 SDK：[WTapi](https://github.com/heerxingen/WTapi)

## 许可

MIT
