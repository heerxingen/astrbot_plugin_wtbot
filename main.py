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

from astrbot.api.event import filter, AstrMessageEvent
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
                lines.append(f"  {self._safe(p, 'name')} ({self._safe(p, 'slug')}) — {self._safe(p, 'web')}")
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
                lines.append(f"  {self._safe(c, 'name')} ({self._safe(c, 'slug')})")
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
    # 生命周期
    # ================================================================

    async def terminate(self):
        self._wt = None
        self._cache_dir = None
