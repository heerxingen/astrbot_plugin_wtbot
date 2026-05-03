"""WTBot — Weblate 翻译管理机器人插件。

用户通过自然语言与 Weblate 交互，LLM 自动调度对应的 Tool。
"""

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star
from astrbot.api import AstrBotConfig, logger

from wtapi import WeblateBot, WeblateError


# ---------------------------------------------------------------------------
# 插件
# ---------------------------------------------------------------------------

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

    # ---- 格式化辅助 ----

    @staticmethod
    def _safe(obj, *keys: str, default: str = "-") -> str:
        for k in keys:
            if isinstance(obj, dict):
                obj = obj.get(k, default)
            else:
                return str(obj) if obj is not None else default
        return str(obj) if obj is not None else default

    @staticmethod
    def _check_config(wt: WeblateBot) -> str | None:
        """Verifica que o bot tenha url e token configurados."""
        if not wt:
            return "请先在插件配置中设置 weblate_url 和 weblate_token"
        return None

    # ================================================================
    # LLM Tools
    # ================================================================

    @filter.llm_tool(name="weblate_list_projects")
    async def list_projects(self, event: AstrMessageEvent) -> MessageEventResult:
        '''列出 Weblate 上的所有翻译项目。用户询问"有哪些项目"、"项目列表"时调用。

        '''
        try:
            cache_key = "projects"
            cached = self._cache_get(cache_key)
            if cached is not None:
                projects = cached
            else:
                projects = await asyncio.to_thread(lambda: list(self.wt.list_projects()))
                self._cache_set(cache_key, projects)

            if not projects:
                yield event.plain_result("没有任何翻译项目。")
                return

            lines = []
            for p in projects:
                lines.append(f"  **{self._safe(p, 'name')}** (`{self._safe(p, 'slug')}`)")
                lines.append(f"    {self._safe(p, 'web')}")
            yield event.plain_result(f"共 {len(projects)} 个项目：\n" + "\n".join(lines))
        except WeblateError as e:
            yield event.plain_result(f"Weblate API 错误 [{e.status_code}]: {e.detail}")
        except RuntimeError as e:
            yield event.plain_result(str(e))
        except Exception as e:
            logger.error(f"list_projects failed: {e}")
            yield event.plain_result(f"请求失败: {e}")

    @filter.llm_tool(name="weblate_list_components")
    async def list_components(
        self, event: AstrMessageEvent, project_slug: str
    ) -> MessageEventResult:
        '''列出某个翻译项目下的所有组件。

        Args:
            project_slug(string): 项目 slug，从 list_projects 结果中获取
        '''
        try:
            cache_key = f"components_{project_slug}"
            cached = self._cache_get(cache_key)
            if cached is not None:
                comps = cached
            else:
                comps = await asyncio.to_thread(lambda: list(self.wt.list_project_components(project_slug)))
                self._cache_set(cache_key, comps)

            if not comps:
                yield event.plain_result(f"项目 `{project_slug}` 下没有任何组件。")
                return

            lines = []
            for c in comps:
                lines.append(f"  **{self._safe(c, 'name')}** (`{self._safe(c, 'slug')}`)")
                lines.append(f"    仓库: {self._safe(c, 'repo')}  分支: {self._safe(c, 'branch')}")
                lines.append(f"    文件: {self._safe(c, 'filemask')}  格式: {self._safe(c, 'file_format')}")
            yield event.plain_result(f"项目 `{project_slug}` 共 {len(comps)} 个组件：\n" + "\n".join(lines))
        except WeblateError as e:
            yield event.plain_result(f"Weblate API 错误 [{e.status_code}]: {e.detail}")
        except RuntimeError as e:
            yield event.plain_result(str(e))
        except Exception as e:
            logger.error(f"list_components failed: {e}")
            yield event.plain_result(f"请求失败: {e}")

    @filter.llm_tool(name="weblate_translation_status")
    async def translation_status(
        self, event: AstrMessageEvent, project_slug: str, component_slug: str
    ) -> MessageEventResult:
        '''查看某组件的翻译进度统计，包含各语言的翻译百分比、未翻译数等。

        Args:
            project_slug(string): 项目 slug
            component_slug(string): 组件 slug
        '''
        try:
            cache_key = f"translations_{project_slug}_{component_slug}"
            cached = self._cache_get(cache_key)
            if cached is not None:
                translations = cached
            else:
                translations = await asyncio.to_thread(
                    lambda: list(self.wt.list_component_translations(project_slug, component_slug))
                )
                self._cache_set(cache_key, translations)

            if not translations:
                yield event.plain_result(f"`{project_slug}/{component_slug}` 没有翻译。")
                return

            lines = [f"**{project_slug}/{component_slug}** 翻译进度：\n"]
            for t in translations:
                lang_name = self._safe(t, "language", "name")
                lang_code = self._safe(t, "language_code")
                pct = self._safe(t, "translated_percent", default="0")
                total = self._safe(t, "total", default="?")
                trans = self._safe(t, "translated", default="?")
                fuzzy = self._safe(t, "fuzzy", default="0")
                failing = self._safe(t, "failing_checks", default="0")
                bar = self._pct_bar(float(pct))
                lines.append(f"  {bar} {lang_name} ({lang_code}) — {pct}% ({trans}/{total})  fuzzy:{fuzzy} fail:{failing}")
            yield event.plain_result("\n".join(lines))
        except WeblateError as e:
            yield event.plain_result(f"Weblate API 错误 [{e.status_code}]: {e.detail}")
        except RuntimeError as e:
            yield event.plain_result(str(e))
        except Exception as e:
            logger.error(f"translation_status failed: {e}")
            yield event.plain_result(f"请求失败: {e}")

    @staticmethod
    def _pct_bar(pct: float) -> str:
        filled = round(pct / 10)
        bar = "█" * filled + "░" * (10 - filled)
        return bar

    @filter.llm_tool(name="weblate_translation_changes")
    async def translation_changes(
        self,
        event: AstrMessageEvent,
        project_slug: str,
        component_slug: str,
        lang: str = "",
        hours: int = 24,
    ) -> MessageEventResult:
        '''查看翻译变更历史。用户询问"最近有谁改了翻译"、"最近的变化"时调用。

        Args:
            project_slug(string): 项目 slug
            component_slug(string): 组件 slug
            lang(string): 语言代码，可选，如 zh_Hans。不填则显示所有语言
            hours(number): 查看最近多少小时的变更，默认 24
        '''
        try:
            since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            params: dict[str, str] = {"timestamp_after": since}
            if lang:
                changes = await asyncio.to_thread(
                    lambda: list(self.wt.list_translation_changes(project_slug, component_slug, lang, **params))
                )
            else:
                changes = await asyncio.to_thread(
                    lambda: list(self.wt.list_component_changes(project_slug, component_slug, **params))
                )

            if not changes:
                yield event.plain_result(f"`{project_slug}/{component_slug}` 最近 {hours} 小时内没有变更。")
                return

            limit = min(len(changes), 20)
            lines = [f"**{project_slug}/{component_slug}** 最近 {hours} 小时变更（{limit}/{len(changes)}）：\n"]
            for ch in changes[:20]:
                ts = self._safe(ch, "timestamp")[:19]
                user = self._safe(ch, "user", default="系统").split("/")[-2] if "/" in str(ch.get("user", "")) else self._safe(ch, "author", default="系统")
                action = self._safe(ch, "action_name")
                old = self._safe(ch, "old", default="") or ""
                target = self._safe(ch, "target", default="") or ""
                if old:
                    old = f" ← {old[:40]}"
                if target:
                    target = f" → {target[:40]}"
                lines.append(f"  `{ts}` {user}: {action}{old}{target}")
            yield event.plain_result("\n".join(lines))
        except WeblateError as e:
            yield event.plain_result(f"Weblate API 错误 [{e.status_code}]: {e.detail}")
        except RuntimeError as e:
            yield event.plain_result(str(e))
        except Exception as e:
            logger.error(f"translation_changes failed: {e}")
            yield event.plain_result(f"请求失败: {e}")

    @filter.llm_tool(name="weblate_repository_status")
    async def repository_status(
        self,
        event: AstrMessageEvent,
        project_slug: str,
        component_slug: str = "",
    ) -> MessageEventResult:
        '''查看 VCS 仓库状态 — 是否有待提交、待推送的变更。用户问"仓库状态"时调用。

        Args:
            project_slug(string): 项目 slug
            component_slug(string): 组件 slug，可选。不填则显示该项目所有组件的仓库状态
        '''
        try:
            if component_slug:
                repo = await asyncio.to_thread(
                    self.wt.get_component_repository, project_slug, component_slug
                )
                yield event.plain_result(
                    f"`{project_slug}/{component_slug}` 仓库状态：\n"
                    f"  needs_commit: {repo.get('needs_commit', '-')}\n"
                    f"  needs_merge:  {repo.get('needs_merge', '-')}\n"
                    f"  needs_push:   {repo.get('needs_push', '-')}\n"
                    f"  status: {repo.get('status', '-')}"
                )
                return

            # 所有组件
            comps = await asyncio.to_thread(
                lambda: list(self.wt.list_project_components(project_slug))
            )
            lines = [f"**{project_slug}** 仓库状态：\n"]
            for c in comps:
                slug = self._safe(c, "slug")
                try:
                    repo = await asyncio.to_thread(
                        self.wt.get_component_repository, project_slug, slug
                    )
                except WeblateError:
                    lines.append(f"  `{slug}`: 无法获取")
                    continue
                flags = []
                if repo.get("needs_commit"):
                    flags.append("C")
                if repo.get("needs_merge"):
                    flags.append("M")
                if repo.get("needs_push"):
                    flags.append("P")
                status = ",".join(flags) if flags else "ok"
                lines.append(f"  `{slug}`: {status}")
            yield event.plain_result("\n".join(lines))
        except WeblateError as e:
            yield event.plain_result(f"Weblate API 错误 [{e.status_code}]: {e.detail}")
        except RuntimeError as e:
            yield event.plain_result(str(e))
        except Exception as e:
            logger.error(f"repository_status failed: {e}")
            yield event.plain_result(f"请求失败: {e}")

    @filter.llm_tool(name="weblate_repository_pull")
    async def repository_pull(
        self, event: AstrMessageEvent, project_slug: str, component_slug: str
    ) -> MessageEventResult:
        '''从远程仓库拉取最新翻译文件到 Weblate。用户说"拉取仓库"、"更新"时调用。
        注意：执行前请让用户确认。

        Args:
            project_slug(string): 项目 slug
            component_slug(string): 组件 slug
        '''
        try:
            result = await asyncio.to_thread(
                self.wt.repo_component, project_slug, component_slug, "pull"
            )
            self._cache_clear_prefix("")
            yield event.plain_result(
                f"已拉取 `{project_slug}/{component_slug}` 仓库。\n结果: {result.get('result', '-')}"
            )
        except WeblateError as e:
            yield event.plain_result(f"Weblate API 错误 [{e.status_code}]: {e.detail}")
        except RuntimeError as e:
            yield event.plain_result(str(e))
        except Exception as e:
            logger.error(f"repository_pull failed: {e}")
            yield event.plain_result(f"请求失败: {e}")

    @filter.llm_tool(name="weblate_repository_push")
    async def repository_push(
        self, event: AstrMessageEvent, project_slug: str, component_slug: str
    ) -> MessageEventResult:
        '''将 Weblate 的翻译变更推送到远程仓库。用户说"推送翻译"、"push"时调用。
        注意：执行前请让用户确认。

        Args:
            project_slug(string): 项目 slug
            component_slug(string): 组件 slug
        '''
        try:
            result = await asyncio.to_thread(
                self.wt.repo_component, project_slug, component_slug, "push"
            )
            self._cache_clear_prefix("")
            yield event.plain_result(
                f"已推送 `{project_slug}/{component_slug}`。\n结果: {result.get('result', '-')}"
            )
        except WeblateError as e:
            yield event.plain_result(f"Weblate API 错误 [{e.status_code}]: {e.detail}")
        except RuntimeError as e:
            yield event.plain_result(str(e))
        except Exception as e:
            logger.error(f"repository_push failed: {e}")
            yield event.plain_result(f"请求失败: {e}")

    @filter.llm_tool(name="weblate_search_unit")
    async def search_unit(
        self,
        event: AstrMessageEvent,
        project_slug: str,
        component_slug: str,
        lang: str,
        query: str,
    ) -> MessageEventResult:
        '''在翻译单元中搜索关键词。用户问"xxx 怎么翻译的"、"搜索翻译"时调用。

        Args:
            project_slug(string): 项目 slug
            component_slug(string): 组件 slug
            lang(string): 语言代码，如 zh_Hans, en
            query(string): 搜索关键词
        '''
        try:
            units = await asyncio.to_thread(
                lambda: list(self.wt.list_translation_units(project_slug, component_slug, lang, q=query))
            )
            if not units:
                yield event.plain_result(f"在 `{project_slug}/{component_slug}/{lang}` 中未找到 `{query}` 的翻译。")
                return

            limit = min(len(units), 15)
            lines = [f"搜索 `{query}` 在 {project_slug}/{component_slug}/{lang}（{limit}/{len(units)}）：\n"]
            for u in units[:15]:
                src = self._safe(u, "source", default="") or ""
                if isinstance(u.get("source"), list):
                    src = " | ".join(u["source"])
                tgt = self._safe(u, "target", default="(未翻译)") or "(未翻译)"
                if isinstance(u.get("target"), list):
                    tgt = " | ".join(u.get("target", ["(未翻译)"]))
                state = {0: "空", 10: "需编辑", 20: "已译", 30: "已核准"}.get(
                    int(self._safe(u, "state", default="0")), "?"
                )
                lines.append(f"  [{state}] #{self._safe(u, 'id')} {src[:60]}")
                lines.append(f"         → {tgt[:80]}")
            yield event.plain_result("\n".join(lines))
        except WeblateError as e:
            yield event.plain_result(f"Weblate API 错误 [{e.status_code}]: {e.detail}")
        except RuntimeError as e:
            yield event.plain_result(str(e))
        except Exception as e:
            logger.error(f"search_unit failed: {e}")
            yield event.plain_result(f"请求失败: {e}")

    @filter.llm_tool(name="weblate_translate_unit")
    async def translate_unit(
        self, event: AstrMessageEvent, unit_id: int, target: str
    ) -> MessageEventResult:
        '''修改单个翻译单元的内容。用户说"把第 X 条翻译成 Y"时调用。
        执行前让用户确认修改内容。

        Args:
            unit_id(number): 翻译单元 ID
            target(string): 目标语言翻译文本
        '''
        try:
            result = await asyncio.to_thread(
                self.wt.update_unit, unit_id, target=[target], state=20
            )
            src = ""
            if isinstance(result.get("source"), list):
                src = " | ".join(result["source"])
            yield event.plain_result(
                f"已翻译 #{unit_id}\n  {src[:80]}\n  → {target}"
            )
        except WeblateError as e:
            yield event.plain_result(f"Weblate API 错误 [{e.status_code}]: {e.detail}")
        except RuntimeError as e:
            yield event.plain_result(str(e))
        except Exception as e:
            logger.error(f"translate_unit failed: {e}")
            yield event.plain_result(f"请求失败: {e}")

    @filter.llm_tool(name="weblate_language_stats")
    async def language_stats(
        self, event: AstrMessageEvent, lang_code: str
    ) -> MessageEventResult:
        '''查看某个语言在所有项目中的翻译统计。用户问"中文翻译情况"时调用。

        Args:
            lang_code(string): 语言代码，如 zh_Hans, en, ja
        '''
        try:
            stats = await asyncio.to_thread(self.wt.get_language_statistics, lang_code)
            yield event.plain_result(
                f"语言 **{lang_code}** 统计：\n"
                f"  翻译条目: {stats.get('translated', 0)}\n"
                f"  总条目:   {stats.get('total', 0)}\n"
                f"  完成率:   {stats.get('translated_percent', 0)}%\n"
                f"  待编辑:   {stats.get('fuzzy', 0)}\n"
                f"  失败检查: {stats.get('failing', 0)}"
            )
        except WeblateError as e:
            yield event.plain_result(f"Weblate API 错误 [{e.status_code}]: {e.detail}")
        except RuntimeError as e:
            yield event.plain_result(str(e))
        except Exception as e:
            logger.error(f"language_stats failed: {e}")
            yield event.plain_result(f"请求失败: {e}")

    # ================================================================
    # 生命周期
    # ================================================================

    async def terminate(self):
        """插件卸载时清理。"""
        self._wt = None
        self._cache_dir = None
