"""WTBot — Weblate 翻译管理机器人插件。

用户通过自然语言与 Weblate 交互，LLM 自动调度对应的 Tool。
Tool 函数返回字符串结果，LLM 可连续调用多个 Tool。
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star
from astrbot.api import AstrBotConfig, logger

from wtapi import WeblateBot, WeblateError


class WTBot(Star):
    """Weblate 翻译管理插件 — 提供 LLM Tools 供 AI 自动调用。"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._wt: WeblateBot | None = None
        self._cache_dir: Path | None = None

    # ---- 懒加载 ----

    @property
    def wt(self) -> WeblateBot:
        if self._wt is None:
            url = (self.config.get("weblate_url") or "").strip()
            token = (self.config.get("weblate_token") or "").strip()
            if not url or not token:
                raise RuntimeError("请先在插件配置中设置 weblate_url 和 weblate_token")
            self._wt = WeblateBot(url, token)
        return self._wt

    @property
    def cache_dir(self) -> Path:
        if self._cache_dir is None:
            p = Path("data/plugin_data/wtbot/cache")
            p.mkdir(parents=True, exist_ok=True)
            self._cache_dir = p
        return self._cache_dir

    @property
    def ttl(self) -> int:
        return max(0, int(self.config.get("cache_ttl", 300)))

    # ---- 缓存 ----

    def _cache_get(self, key: str) -> object | None:
        if self.ttl == 0:
            return None
        f = self.cache_dir / f"{key}.json"
        if not f.exists():
            return None
        try:
            data = json.loads(f.read_text())
            ts = datetime.fromisoformat(data["ts"])
            if (datetime.now() - ts).total_seconds() < self.ttl:
                return data["payload"]
        except Exception:
            pass
        return None

    def _cache_set(self, key: str, payload: object) -> None:
        if self.ttl == 0:
            return
        f = self.cache_dir / f"{key}.json"
        f.write_text(json.dumps({"ts": datetime.now().isoformat(), "payload": payload}))

    def _cache_clear_prefix(self, prefix: str) -> None:
        for f in self.cache_dir.glob(f"{prefix}*.json"):
            f.unlink(missing_ok=True)

    # ---- 辅助 ----

    @staticmethod
    def _safe(obj, *keys: str, default: str = "-") -> str:
        for k in keys:
            if isinstance(obj, dict):
                obj = obj.get(k, default)
            else:
                return str(obj) if obj is not None else default
        return str(obj) if obj is not None else default

    @staticmethod
    def _pct_bar(pct: float) -> str:
        filled = round(pct / 10)
        return "█" * filled + "░" * (10 - filled)

    def _resolve_project(self, project_slug: str) -> str:
        """项目 slug 为空时回退到配置的默认项目。"""
        return project_slug or (self.config.get("default_project") or "").strip()

    def _handle_err(self, name: str, e: Exception) -> str:
        if isinstance(e, WeblateError):
            return f"Weblate API 错误 [{e.status_code}]: {e.detail}"
        if isinstance(e, RuntimeError):
            return str(e)
        logger.error(f"{name} failed: {e}")
        return f"请求失败: {e}"

    # ================================================================
    # LLM Tools — 返回字符串，LLM 可连续调用
    # ================================================================

    @filter.llm_tool(name="weblate_list_projects")
    async def list_projects(self, event: AstrMessageEvent) -> str:
        '''列出 Weblate 上的所有翻译项目。用户询问"有哪些项目"、"项目列表"时调用。'''
        try:
            cache_key = "projects"
            cached = self._cache_get(cache_key)
            projects = cached if cached is not None else \
                await asyncio.to_thread(lambda: list(self.wt.list_projects()))
            if cached is None:
                self._cache_set(cache_key, projects)

            if not projects:
                return "没有任何翻译项目。"

            lines = []
            for p in projects:
                lines.append(f"  {self._safe(p, 'name')} (slug: {self._safe(p, 'slug')})")
            return f"共 {len(projects)} 个项目：\n" + "\n".join(lines)
        except Exception as e:
            return self._handle_err("list_projects", e)

    @filter.llm_tool(name="weblate_list_components")
    async def list_components(self, event: AstrMessageEvent, project_slug: str = "") -> str:
        '''列出翻译项目下的所有组件。

        Args:
            project_slug(string): 项目 slug，可选，默认使用配置的默认项目
        '''
        project_slug = self._resolve_project(project_slug)
        try:
            cache_key = f"components_{project_slug}"
            cached = self._cache_get(cache_key)
            comps = cached if cached is not None else \
                await asyncio.to_thread(lambda: list(self.wt.list_project_components(project_slug)))
            if cached is None:
                self._cache_set(cache_key, comps)

            if not comps:
                return f"项目 {project_slug} 下没有任何组件。"

            lines = []
            for c in comps:
                lines.append(f"  {self._safe(c, 'name')} (slug: {self._safe(c, 'slug')})")
                lines.append(f"    repo: {self._safe(c, 'repo')}  branch: {self._safe(c, 'branch')}")
                lines.append(f"    filemask: {self._safe(c, 'filemask')}  format: {self._safe(c, 'file_format')}")
            return f"项目 {project_slug} 共 {len(comps)} 个组件：\n" + "\n".join(lines)
        except Exception as e:
            return self._handle_err("list_components", e)

    @filter.llm_tool(name="weblate_translation_status")
    async def translation_status(
        self, event: AstrMessageEvent, project_slug: str = "", component_slug: str = ""
    ) -> str:
        '''查看翻译进度统计。用户说"翻译进度"、"还有多少没翻"时调用。

        Args:
            project_slug(string): 项目 slug，可选，默认使用配置的默认项目
            component_slug(string): 组件 slug
        '''
        project_slug = self._resolve_project(project_slug)
        try:
            cache_key = f"translations_{project_slug}_{component_slug}"
            cached = self._cache_get(cache_key)
            translations = cached if cached is not None else \
                await asyncio.to_thread(
                    lambda: list(self.wt.list_component_translations(project_slug, component_slug)))
            if cached is None:
                self._cache_set(cache_key, translations)

            if not translations:
                return f"{project_slug}/{component_slug} 没有翻译。"

            lines = [f"{project_slug}/{component_slug} 翻译进度："]
            for t in translations:
                lang_name = self._safe(t, "language", "name")
                lang_code = self._safe(t, "language_code")
                pct = float(self._safe(t, "translated_percent", default="0"))
                total = self._safe(t, "total", default="?")
                trans = self._safe(t, "translated", default="?")
                fuzzy = self._safe(t, "fuzzy", default="0")
                failing = self._safe(t, "failing_checks", default="0")
                bar = self._pct_bar(pct)
                lines.append(
                    f"  {bar} {lang_name} ({lang_code}) — {pct}% ({trans}/{total})  fuzzy:{fuzzy} fail:{failing}"
                )
            return "\n".join(lines)
        except Exception as e:
            return self._handle_err("translation_status", e)

    @filter.llm_tool(name="weblate_translation_changes")
    async def translation_changes(
        self, event: AstrMessageEvent,
        project_slug: str = "", component_slug: str = "",
        lang: str = "", hours: int = 24,
    ) -> str:
        '''查看翻译变更历史。用户询问"最近有谁改了翻译"时调用。

        Args:
            project_slug(string): 项目 slug，可选，默认使用配置的默认项目
            component_slug(string): 组件 slug
            lang(string): 语言代码，可选，如 zh_Hans。不填则显示所有语言
            hours(number): 最近多少小时，默认 24
        '''
        project_slug = self._resolve_project(project_slug)
        try:
            since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            params = {"timestamp_after": since}
            if lang:
                changes = await asyncio.to_thread(
                    lambda: list(self.wt.list_translation_changes(project_slug, component_slug, lang, **params)))
            else:
                changes = await asyncio.to_thread(
                    lambda: list(self.wt.list_component_changes(project_slug, component_slug, **params)))

            if not changes:
                return f"{project_slug}/{component_slug} 最近 {hours} 小时内没有变更。"

            limit = min(len(changes), 20)
            lines = [f"{project_slug}/{component_slug} 最近 {hours}h 变更 ({limit}/{len(changes)})："]
            for ch in changes[:20]:
                ts = (self._safe(ch, "timestamp"))[:19]
                raw = ch.get("user", "")
                user = raw.split("/")[-2] if raw and "/" in str(raw) else self._safe(ch, "author", default="系统")
                action = self._safe(ch, "action_name")
                old = f" ← {str(ch.get('old', ''))[:40]}" if ch.get("old") else ""
                tgt = f" → {str(ch.get('target', ''))[:40]}" if ch.get("target") else ""
                lines.append(f"  {ts} {user}: {action}{old}{tgt}")
            return "\n".join(lines)
        except Exception as e:
            return self._handle_err("translation_changes", e)

    @filter.llm_tool(name="weblate_repository_status")
    async def repository_status(
        self, event: AstrMessageEvent,
        project_slug: str = "", component_slug: str = "",
    ) -> str:
        '''查看 VCS 仓库状态。用户问"仓库状态"、"有没有待推送"时调用。

        Args:
            project_slug(string): 项目 slug，可选，默认使用配置的默认项目
            component_slug(string): 组件 slug，可选。不填则显示所有组件
        '''
        project_slug = self._resolve_project(project_slug)
        try:
            if component_slug:
                repo = await asyncio.to_thread(
                    self.wt.get_component_repository, project_slug, component_slug)
                return (
                    f"{project_slug}/{component_slug} 仓库状态：\n"
                    f"  needs_commit: {repo.get('needs_commit', '-')}\n"
                    f"  needs_merge:  {repo.get('needs_merge', '-')}\n"
                    f"  needs_push:   {repo.get('needs_push', '-')}\n"
                    f"  status: {repo.get('status', '-')}"
                )

            comps = await asyncio.to_thread(
                lambda: list(self.wt.list_project_components(project_slug)))
            lines = [f"{project_slug} 仓库状态："]
            for c in comps:
                slug = self._safe(c, "slug")
                try:
                    repo = await asyncio.to_thread(
                        self.wt.get_component_repository, project_slug, slug)
                except WeblateError:
                    lines.append(f"  {slug}: 无法获取")
                    continue
                flags = []
                if repo.get("needs_commit"): flags.append("C")
                if repo.get("needs_merge"):  flags.append("M")
                if repo.get("needs_push"):   flags.append("P")
                lines.append(f"  {slug}: {','.join(flags) if flags else 'ok'}")
            return "\n".join(lines)
        except Exception as e:
            return self._handle_err("repository_status", e)

    @filter.llm_tool(name="weblate_repository_pull")
    async def repository_pull(
        self, event: AstrMessageEvent, project_slug: str = "", component_slug: str = ""
    ) -> str:
        '''从远程仓库拉取最新翻译文件。执行前建议让用户确认。

        Args:
            project_slug(string): 项目 slug，可选，默认使用配置的默认项目
            component_slug(string): 组件 slug
        '''
        project_slug = self._resolve_project(project_slug)
        try:
            result = await asyncio.to_thread(
                self.wt.repo_component, project_slug, component_slug, "pull")
            self._cache_clear_prefix("")
            return f"已拉取 {project_slug}/{component_slug} 仓库。result: {result.get('result', '-')}"
        except Exception as e:
            return self._handle_err("repository_pull", e)

    @filter.llm_tool(name="weblate_repository_push")
    async def repository_push(
        self, event: AstrMessageEvent, project_slug: str = "", component_slug: str = ""
    ) -> str:
        '''推送 Weblate 翻译变更到远程仓库。执行前建议让用户确认。

        Args:
            project_slug(string): 项目 slug，可选，默认使用配置的默认项目
            component_slug(string): 组件 slug
        '''
        project_slug = self._resolve_project(project_slug)
        try:
            result = await asyncio.to_thread(
                self.wt.repo_component, project_slug, component_slug, "push")
            self._cache_clear_prefix("")
            return f"已推送 {project_slug}/{component_slug}。result: {result.get('result', '-')}"
        except Exception as e:
            return self._handle_err("repository_push", e)

    @filter.llm_tool(name="weblate_search_unit")
    async def search_unit(
        self, event: AstrMessageEvent,
        project_slug: str = "", component_slug: str = "", lang: str = "", query: str = "",
    ) -> str:
        '''在翻译单元中搜索关键词。用户问"xxx 怎么翻译的"时调用。

        Args:
            project_slug(string): 项目 slug，可选，默认使用配置的默认项目
            component_slug(string): 组件 slug
            lang(string): 语言代码，如 zh_Hans
            query(string): 搜索关键词
        '''
        project_slug = self._resolve_project(project_slug)
        try:
            units = await asyncio.to_thread(
                lambda: list(self.wt.list_translation_units(project_slug, component_slug, lang, q=query)))

            if not units:
                return f"在 {project_slug}/{component_slug}/{lang} 中未找到 '{query}' 的翻译。"

            limit = min(len(units), 15)
            lines = [f"搜索 '{query}' in {project_slug}/{component_slug}/{lang} ({limit}/{len(units)})："]
            for u in units[:15]:
                src = u.get("source", "")
                if isinstance(src, list):
                    src = " | ".join(src)
                tgt = u.get("target", "(未翻译)")
                if isinstance(tgt, list):
                    tgt = " | ".join(tgt) if tgt else "(未翻译)"
                state_map = {0: "空", 10: "需编辑", 20: "已译", 30: "已核准"}
                st = state_map.get(int(self._safe(u, "state", default="0")), "?")
                lines.append(f"  [{st}] #{self._safe(u, 'id')} {str(src)[:60]}")
                lines.append(f"         → {str(tgt)[:80]}")
            return "\n".join(lines)
        except Exception as e:
            return self._handle_err("search_unit", e)

    @filter.llm_tool(name="weblate_translate_unit")
    async def translate_unit(
        self, event: AstrMessageEvent, unit_id: int, target: str
    ) -> str:
        '''修改单个翻译单元。执行前建议让用户确认内容。

        Args:
            unit_id(number): 翻译单元 ID
            target(string): 目标语言翻译文本
        '''
        try:
            result = await asyncio.to_thread(
                self.wt.update_unit, unit_id, target=[target], state=20)
            src = ""
            if isinstance(result.get("source"), list):
                src = " | ".join(result["source"])
            return f"已翻译 #{unit_id}\n  {str(src)[:80]}\n  -> {target}"
        except Exception as e:
            return self._handle_err("translate_unit", e)

    @filter.llm_tool(name="weblate_language_stats")
    async def language_stats(self, event: AstrMessageEvent, lang_code: str) -> str:
        '''查看某个语言在所有项目中的翻译统计。

        Args:
            lang_code(string): 语言代码，如 zh_Hans, en, ja
        '''
        try:
            stats = await asyncio.to_thread(self.wt.get_language_statistics, lang_code)
            return (
                f"语言 {lang_code} 统计：\n"
                f"  翻译条目: {stats.get('translated', 0)}\n"
                f"  总条目:   {stats.get('total', 0)}\n"
                f"  完成率:   {stats.get('translated_percent', 0)}%\n"
                f"  待编辑:   {stats.get('fuzzy', 0)}\n"
                f"  失败检查: {stats.get('failing', 0)}"
            )
        except Exception as e:
            return self._handle_err("language_stats", e)

    # ================================================================
    # 模板系统
    # ================================================================

    _TEMPLATE_SYSTEM_PROMPT = (
        "你是一个翻译项目模板助手。用户会描述需要创建的字符串模板规则，"
        "你将其整理为简洁的自然语言模板描述。\n\n"
        "模板描述应包含：\n"
        "- 何时使用该模板\n"
        "- 目标组件\n"
        "- key 和 source 的格式规则\n"
        "- 已知的中英名称映射\n\n"
        "重要规则：\n"
        "- 若 key 中需要包含项目专有名词（角色名、武器名、地名等），"
        "必须在模板描述中明确注明\"这些名词需用户提供英文翻译，禁止自行音译或意译\"，"
        "以便后续 LLM 执行时不会擅自翻译\n"
        "- 只写规则，不写示例代码或 JSON\n"
        "- 用中文"
    )

    @property
    def _tpl_path(self) -> Path:
        return Path("data/plugin_data/wtbot/templates.json")

    def _tpl_enabled(self) -> bool:
        return bool(self.config.get("enable_templates", False))

    def _load_templates(self) -> dict:
        if not self._tpl_path.exists():
            return {}
        try:
            return json.loads(self._tpl_path.read_text())
        except Exception:
            return {}

    def _save_templates(self, data: dict) -> None:
        self._tpl_path.parent.mkdir(parents=True, exist_ok=True)
        self._tpl_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    async def _tpl_call_ai(self, event: AstrMessageEvent, prompt: str) -> str:
        """调用 AI 模型生成模板描述。"""
        provider_id = (self.config.get("template_ai_provider") or "").strip()
        if not provider_id:
            provider_id = await self.context.get_current_chat_provider_id(
                event.unified_msg_origin)
        # request has no timeout param, but ContextWrapper may pass it
        resp = await self.context.llm_generate(
            chat_provider_id=provider_id,
            prompt=prompt,
        )
        return resp.completion_text

    # ---- 返回 str 的 Tool（可 chain） ----

    @filter.llm_tool(name="weblate_list_templates")
    async def list_templates(self, event: AstrMessageEvent) -> str:
        '''列出所有可用的字符串模板及其作用。'''
        if not self._tpl_enabled():
            return "模板功能未启用，请在插件配置中开启 enable_templates。"
        try:
            templates = self._load_templates()
            if not templates:
                return "当前没有任何字符串模板。可以通过对话创建。"
            lines = ["可用模板："]
            for slug, tpl in templates.items():
                lines.append(f"  {tpl.get('name', slug)} (slug: {slug}) — {tpl.get('description', '')[:80]}")
            return "\n".join(lines)
        except Exception as e:
            return self._handle_err("list_templates", e)

    @filter.llm_tool(name="weblate_show_template")
    async def show_template(self, event: AstrMessageEvent, template_name: str) -> str:
        '''查看指定模板的完整自然语言描述。

        Args:
            template_name(string): 模板 slug
        '''
        if not self._tpl_enabled():
            return "模板功能未启用。"
        try:
            templates = self._load_templates()
            tpl = templates.get(template_name)
            if not tpl:
                return f"模板 {template_name} 不存在。可用模板: {', '.join(templates.keys())}"
            return (
                f"模板 **{tpl.get('name', template_name)}** ({template_name})：\n\n"
                f"{tpl.get('description', '')}\n\n"
                f"目标组件: {tpl.get('component', '未指定')}"
            )
        except Exception as e:
            return self._handle_err("show_template", e)

    @filter.llm_tool(name="weblate_create_unit")
    async def create_unit(
        self, event: AstrMessageEvent,
        component: str = "", lang: str = "", key: str = "", value: str = "",
    ) -> str:
        '''创建单个翻译单元。LLM 根据模板描述推断出 key/value/component/lang 后调用。

        Args:
            component(string): 目标组件 slug
            lang(string): 语言代码，如 en
            key(string): 翻译 key
            value(string): source 源字符串
        '''
        if not component or not key or not value:
            return "缺少必要参数: component, key, value" + f" (got component={component}, key={key}, value={value})"
        default_lang = (self.config.get("default_lang") or "en").strip()
        lang = lang or default_lang
        try:
            result = await asyncio.to_thread(
                self.wt.create_unit,
                self._resolve_project(""), component, lang,
                key=key, value=[value],
            )
            uid = result.get("id", "?")
            return f"已创建 unit #{uid}: key={key}, value={value}, lang={lang}, component={component}"
        except Exception as e:
            return self._handle_err("create_unit", e)

    # ---- yield plain_result 的 Tool（直接输出用户） ----

    @filter.llm_tool(name="weblate_create_template")
    async def create_template(self, event: AstrMessageEvent, requirement: str) -> MessageEventResult:
        '''AI 辅助创建字符串模板。用户说"创建一个模板"时调用。
        结果直接展示给用户。

        Args:
            requirement(string): 用户对模板的需求描述。如果用户只说想创建模板但没说内容，传空字符串并让用户补充。
        '''
        if not self._tpl_enabled():
            yield event.plain_result("模板功能未启用，请在插件配置中开启 enable_templates。")
            return
        if not requirement.strip():
            yield event.plain_result("请描述你的模板需求，例如：\"角色出新皮肤时在 Direct Resources 组件创建 Info/角色英文-皮肤英文 格式的字符串\"")
            return
        try:
            templates = self._load_templates()
            full_prompt = (
                f"用户需求：{requirement}\n\n"
                "请根据上述需求生成自然语言模板描述。\n"
                "同时为模板起一个英文 slug（小写+下划线）和中文名称。\n"
                "按以下格式输出（每行一项）：\n"
                "SLUG: xxx\n"
                "NAME: xxx\n"
                "COMPONENT: xxx\n"
                "DESCRIPTION:\n"
                "xxx"
            )
            result = await self._tpl_call_ai(event, full_prompt)
            # Parse AI output
            slug = ""
            name = ""
            component = ""
            desc_lines = []
            in_desc = False
            for line in result.split("\n"):
                l = line.strip()
                if l.upper().startswith("SLUG:"):
                    slug = l.split(":", 1)[1].strip()
                elif l.upper().startswith("NAME:"):
                    name = l.split(":", 1)[1].strip()
                elif l.upper().startswith("COMPONENT:"):
                    component = l.split(":", 1)[1].strip()
                elif l.upper().startswith("DESCRIPTION:") and l != "DESCRIPTION:":
                    desc_lines.append(l.split(":", 1)[1].strip())
                elif in_desc or l.upper() == "DESCRIPTION:":
                    in_desc = True
                    continue
                elif in_desc:
                    desc_lines.append(l)
                elif slug and not l:
                    in_desc = True

            # Fallback: if not parsed, use raw result
            if not slug:
                slug = requirement.strip()[:30].replace(" ", "_").lower()
            if not name:
                name = requirement.strip()[:40]
            if not desc_lines:
                desc_lines = [result]

            templates[slug] = {
                "name": name,
                "description": "\n".join(desc_lines).strip(),
                "component": component or "?",
            }
            self._save_templates(templates)
            yield event.plain_result(
                f"模板已创建：**{name}** (slug: {slug})\n"
                f"目标组件: {component or '?'}\n\n"
                f"{templates[slug]['description']}"
            )
        except Exception as e:
            logger.error(f"create_template failed: {e}")
            yield event.plain_result(f"创建模板失败: {e}")

    @filter.llm_tool(name="weblate_update_template")
    async def update_template(
        self, event: AstrMessageEvent, template_name: str, requirement: str
    ) -> MessageEventResult:
        '''更新指定模板的自然语言描述。AI 根据 requirement 重写模板。

        Args:
            template_name(string): 模板 slug
            requirement(string): 需要修改的内容描述
        '''
        if not self._tpl_enabled():
            yield event.plain_result("模板功能未启用。")
            return
        try:
            templates = self._load_templates()
            tpl = templates.get(template_name)
            if not tpl:
                yield event.plain_result(f"模板 {template_name} 不存在。可用: {', '.join(templates.keys())}")
                return
            full_prompt = (
                f"当前模板描述：\n{tpl.get('description', '')}\n\n"
                f"修改需求：{requirement}\n\n"
                "请根据修改需求更新模板描述，保持其他规则不变。只输出更新后的描述文本。"
            )
            result = await self._tpl_call_ai(event, full_prompt)
            tpl["description"] = result.strip()
            self._save_templates(templates)
            yield event.plain_result(
                f"模板 **{tpl.get('name', template_name)}** 已更新：\n\n{result}"
            )
        except Exception as e:
            logger.error(f"update_template failed: {e}")
            yield event.plain_result(f"更新模板失败: {e}")

    @filter.llm_tool(name="weblate_delete_template")
    async def delete_template(
        self, event: AstrMessageEvent, template_name: str
    ) -> MessageEventResult:
        '''删除指定模板。

        Args:
            template_name(string): 模板 slug
        '''
        if not self._tpl_enabled():
            yield event.plain_result("模板功能未启用。")
            return
        try:
            templates = self._load_templates()
            tpl = templates.pop(template_name, None)
            if tpl is None:
                yield event.plain_result(f"模板 {template_name} 不存在。")
                return
            self._save_templates(templates)
            yield event.plain_result(f"模板 **{tpl.get('name', template_name)}** 已删除。")
        except Exception as e:
            logger.error(f"delete_template failed: {e}")
            yield event.plain_result(f"删除模板失败: {e}")

    # ================================================================
    # 生命周期
    # ================================================================

    async def terminate(self):
        self._wt = None
        self._cache_dir = None
