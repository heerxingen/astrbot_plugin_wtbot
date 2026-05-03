"""WeblateBot — Python client for the Weblate REST API.

Usage:
    bot = WeblateBot("https://translate.example.com", token="wlu_...")
    for project in bot.list_projects():
        print(project["name"])
"""

from __future__ import annotations

from collections.abc import Iterator
from io import BufferedReader
from typing import TYPE_CHECKING

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from wtapi.types import (
    AddonDict,
    AnnouncementDict,
    CategoryDict,
    ChangeDict,
    ComponentDict,
    ComponentListDict,
    ContributionDict,
    CreditDict,
    GroupDict,
    LabelDict,
    LanguageDict,
    LinkedComponentDict,
    LockDict,
    MemoryDict,
    MemoryLookupResult,
    MetricsDict,
    PluralDict,
    ProjectDict,
    RepoOperationResult,
    RepositoryDict,
    RoleDict,
    ScreenshotDict,
    StatisticsDict,
    TaskDict,
    TranslationDict,
    UnitDict,
    UserDict,
    UserStatisticsDict,
)

if TYPE_CHECKING:
    from typing import Literal

__version__ = "0.1.0"


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class WeblateError(Exception):
    """Raised on non-2xx HTTP responses from the Weblate API."""

    def __init__(self, status_code: int, detail: str, response: requests.Response) -> None:
        self.status_code = status_code
        self.detail = detail
        self.response = response
        super().__init__(f"[{status_code}] {detail}")

    def __repr__(self) -> str:
        return f"WeblateError(status_code={self.status_code}, detail={self.detail!r})"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _file_handle(path: str) -> tuple[str, BufferedReader, str]:
    """Open a file and return (filename, handle, mime_type) for upload."""
    import mimetypes

    fh = open(path, "rb")
    mime, _ = mimetypes.guess_type(path)
    return (path.split("/")[-1], fh, mime or "application/octet-stream")


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class WeblateBot:
    """Lightweight typed client for the Weblate REST API.

    All list methods return generators that auto-paginate.
    All mutation methods raise `WeblateError` on non-2xx responses.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: int = 30,
        max_retries: int = 0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._api = f"{self.base_url}/api"

        self._sess = requests.Session()
        self._sess.headers.update(
            {
                "Authorization": f"Token {token}",
                "User-Agent": f"WTapi/{__version__}",
                "Accept": "application/json",
            }
        )

        if max_retries > 0:
            retry = Retry(total=max_retries, backoff_factor=0.5, status_forcelist=[429, 502, 503, 504])
            adapter = HTTPAdapter(max_retries=retry)
            self._sess.mount("http://", adapter)
            self._sess.mount("https://", adapter)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
        data: dict | None = None,
        files: dict | None = None,
        headers: dict | None = None,
    ) -> requests.Response:
        url = f"{self._api}{path}" if path.startswith("/") else f"{self._api}/{path}"
        resp = self._sess.request(
            method,
            url,
            params=params,
            json=json,
            data=data,
            files=files,
            timeout=self.timeout,
            headers=headers,
        )
        if not resp.ok:
            detail = ""
            try:
                detail = resp.json().get("detail", resp.text[:200])
            except Exception:
                detail = resp.text[:200]
            raise WeblateError(resp.status_code, detail, resp)
        return resp

    def _get(self, path: str, **params: str | int | bool | None) -> requests.Response:
        return self._request("GET", path, params={k: v for k, v in params.items() if v is not None})

    def _post(
        self,
        path: str,
        *,
        json: dict | None = None,
        data: dict | None = None,
        files: dict | None = None,
        **params: str | int,
    ) -> requests.Response:
        return self._request("POST", path, params=params, json=json, data=data, files=files)

    def _put(self, path: str, *, json: dict | None = None) -> requests.Response:
        return self._request("PUT", path, json=json)

    def _patch(self, path: str, *, json: dict | None = None) -> requests.Response:
        return self._request("PATCH", path, json=json)

    def _delete(self, path: str) -> None:
        self._request("DELETE", path)

    def _paginate(self, path: str, **params: str | int | bool | None) -> Iterator[dict]:
        """Auto-paginate through all pages of a list endpoint."""
        url = path
        while url:
            resp = self._get(url, **params) if url == path else self._sess.get(url, timeout=self.timeout)
            # Re-check auth on subsequent pages
            if url != path and not resp.ok:
                detail = ""
                try:
                    detail = resp.json().get("detail", resp.text[:200])
                except Exception:
                    detail = resp.text[:200]
                raise WeblateError(resp.status_code, detail, resp)
            data = resp.json()
            yield from data.get("results", [])
            url = data.get("next")
            params = {}  # only pass params on first request

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def list_projects(self, **filters: str) -> Iterator[ProjectDict]:
        """List all projects."""
        yield from self._paginate("/projects/", **filters)

    def get_project(self, slug: str) -> ProjectDict:
        """Get project by slug."""
        return self._get(f"/projects/{slug}/").json()

    def create_project(self, name: str, slug: str, web: str) -> ProjectDict:
        """Create a new project."""
        return self._post("/projects/", json={"name": name, "slug": slug, "web": web}).json()

    def update_project(self, slug: str, **fields: str | bool) -> ProjectDict:
        """Update project fields. Supports partial update (PATCH)."""
        return self._patch(f"/projects/{slug}/", json=fields).json()

    def delete_project(self, slug: str) -> None:
        """Delete a project."""
        self._delete(f"/projects/{slug}/")

    def list_project_languages(self, slug: str) -> Iterator[dict]:
        """List languages used in a project."""
        yield from self._paginate(f"/projects/{slug}/languages/")

    def list_project_components(self, slug: str) -> Iterator[ComponentDict]:
        """List components in a project."""
        yield from self._paginate(f"/projects/{slug}/components/")

    def create_component(
        self,
        project: str,
        name: str,
        slug: str,
        repo: str,
        branch: str,
        filemask: str,
        file_format: str,
        **extra: str | bool,
    ) -> ComponentDict:
        """Create a component in a project."""
        payload = {
            "name": name,
            "slug": slug,
            "repo": repo,
            "branch": branch,
            "filemask": filemask,
            "file_format": file_format,
            **extra,
        }
        return self._post(f"/projects/{project}/components/", json=payload).json()

    def list_project_changes(self, slug: str, **filters: str | int) -> Iterator[ChangeDict]:
        """List changes in a project. Filters: user, action, timestamp_after, timestamp_before."""
        yield from self._paginate(f"/projects/{slug}/changes/", **filters)

    def get_project_statistics(self, slug: str) -> StatisticsDict:
        """Get project statistics."""
        return self._get(f"/projects/{slug}/statistics/").json()

    def get_project_repository(self, slug: str) -> RepositoryDict:
        """Get VCS repository status for a project."""
        return self._get(f"/projects/{slug}/repository/").json()

    def repo_project(
        self,
        slug: str,
        operation: Literal["push", "pull", "commit", "reset", "cleanup", "file-sync", "file-scan"],
    ) -> RepoOperationResult:
        """Perform VCS operation on project level."""
        return self._post(f"/projects/{slug}/repository/", json={"operation": operation}).json()

    def list_project_labels(self, slug: str) -> Iterator[LabelDict]:
        """List labels for a project."""
        yield from self._paginate(f"/projects/{slug}/labels/")

    def create_project_label(self, slug: str, name: str, color: str) -> LabelDict:
        """Create a label in a project."""
        return self._post(f"/projects/{slug}/labels/", json={"name": name, "color": color}).json()

    def delete_project_label(self, slug: str, label_id: int) -> None:
        """Delete a label from a project."""
        self._delete(f"/projects/{slug}/labels/{label_id}/")

    def list_project_categories(self, slug: str) -> Iterator[CategoryDict]:
        """List categories in a project."""
        yield from self._paginate(f"/projects/{slug}/categories/")

    def get_project_credits(self, slug: str, **filters: str) -> list[CreditDict]:
        """Get credits for a project."""
        return self._get(f"/projects/{slug}/credits/", **filters).json()

    def download_project_file(self, slug: str, *, format: str = "zip", language_code: str = "") -> bytes:
        """Download project translation files."""
        params = {"format": format}
        if language_code:
            params["language_code"] = language_code
        return self._get(f"/projects/{slug}/file/", **params).content

    def list_project_announcements(self, slug: str) -> Iterator[AnnouncementDict]:
        """List announcements for a project."""
        yield from self._paginate(f"/projects/{slug}/announcements/")

    def create_project_announcement(
        self,
        slug: str,
        message: str,
        severity: str = "info",
        *,
        expiry: str | None = None,
        notify: bool = False,
    ) -> AnnouncementDict:
        """Create an announcement for a project."""
        payload: dict = {"message": message, "severity": severity, "notify": notify}
        if expiry:
            payload["expiry"] = expiry
        return self._post(f"/projects/{slug}/announcements/", json=payload).json()

    def delete_project_announcement(self, slug: str, announcement_id: int) -> None:
        """Delete an announcement from a project."""
        self._delete(f"/projects/{slug}/announcements/{announcement_id}/")

    def get_project_machinery_settings(self, slug: str) -> dict:
        """Get machine translation settings for a project."""
        return self._get(f"/projects/{slug}/machinery_settings/").json()

    def set_project_machinery_settings(self, slug: str, service: str, configuration: str) -> dict:
        """Set machine translation settings for a project."""
        return self._post(
            f"/projects/{slug}/machinery_settings/",
            json={"service": service, "configuration": configuration},
        ).json()

    # ------------------------------------------------------------------
    # Components
    # ------------------------------------------------------------------

    def list_components(self, **filters: str) -> Iterator[ComponentDict]:
        """List all components."""
        yield from self._paginate("/components/", **filters)

    def get_component(self, project: str, component: str) -> ComponentDict:
        """Get component details."""
        return self._get(f"/components/{project}/{component}/").json()

    def update_component(self, project: str, component: str, **fields: str | bool | dict) -> ComponentDict:
        """Update component fields (PATCH)."""
        return self._patch(f"/components/{project}/{component}/", json=fields).json()

    def delete_component(self, project: str, component: str) -> None:
        """Delete a component."""
        self._delete(f"/components/{project}/{component}/")

    def list_component_translations(self, project: str, component: str) -> Iterator[TranslationDict]:
        """List translations in a component."""
        yield from self._paginate(f"/components/{project}/{component}/translations/")

    def create_translation(self, project: str, component: str, language_code: str) -> TranslationDict:
        """Create a new translation in a component."""
        return self._post(
            f"/components/{project}/{component}/translations/",
            json={"language_code": language_code},
        ).json()

    def get_component_repository(self, project: str, component: str) -> RepositoryDict:
        """Get VCS repository status for a component."""
        return self._get(f"/components/{project}/{component}/repository/").json()

    def repo_component(
        self,
        project: str,
        component: str,
        operation: Literal["push", "pull", "commit", "reset", "cleanup"],
    ) -> RepoOperationResult:
        """Perform VCS operation on a component."""
        return self._post(
            f"/components/{project}/{component}/repository/", json={"operation": operation}
        ).json()

    def list_component_changes(
        self, project: str, component: str, **filters: str | int
    ) -> Iterator[ChangeDict]:
        """List changes in a component."""
        yield from self._paginate(f"/components/{project}/{component}/changes/", **filters)

    def get_component_statistics(self, project: str, component: str) -> StatisticsDict:
        """Get component statistics."""
        return self._get(f"/components/{project}/{component}/statistics/").json()

    def get_component_lock(self, project: str, component: str) -> LockDict:
        """Get component lock status."""
        return self._get(f"/components/{project}/{component}/lock/").json()

    def set_component_lock(self, project: str, component: str, locked: bool) -> LockDict:
        """Set component lock."""
        return self._post(f"/components/{project}/{component}/lock/", json={"lock": locked}).json()

    def get_component_monolingual_base(self, project: str, component: str) -> bytes:
        """Download the monolingual base file."""
        return self._get(f"/components/{project}/{component}/monolingual_base/").content

    def get_component_new_template(self, project: str, component: str) -> bytes:
        """Download the new translation template."""
        return self._get(f"/components/{project}/{component}/new_template/").content

    def list_component_screenshots(
        self, project: str, component: str
    ) -> Iterator[ScreenshotDict]:
        """List screenshots for a component."""
        yield from self._paginate(f"/components/{project}/{component}/screenshots/")

    def list_component_links(self, project: str, component: str) -> LinkedComponentDict:
        """Get linked components."""
        return self._get(f"/components/{project}/{component}/links/").json()

    def add_component_link(
        self, project: str, component: str, project_slug: str, *, category_id: int | None = None
    ) -> None:
        """Link a component to another project."""
        payload: dict = {"project_slug": project_slug}
        if category_id is not None:
            payload["category_id"] = category_id
        self._post(f"/components/{project}/{component}/links/", json=payload)

    def remove_component_link(self, project: str, component: str, project_slug: str) -> None:
        """Remove a component link."""
        self._delete(f"/components/{project}/{component}/links/{project_slug}/")

    def get_component_credits(self, project: str, component: str, **filters: str) -> list[CreditDict]:
        """Get credits for a component."""
        return self._get(f"/components/{project}/{component}/credits/", **filters).json()

    def get_component_task(self, project: str, component: str) -> TaskDict:
        """Get background task status for a component."""
        return self._get(f"/components/{project}/{component}/task/").json()

    def download_component_file(self, project: str, component: str, *, format: str = "po") -> bytes:
        """Download component translation file."""
        return self._get(f"/components/{project}/{component}/file/", format=format).content

    def list_component_announcements(
        self, project: str, component: str
    ) -> Iterator[AnnouncementDict]:
        """List announcements for a component."""
        yield from self._paginate(f"/components/{project}/{component}/announcements/")

    def create_component_announcement(
        self,
        project: str,
        component: str,
        message: str,
        severity: str = "info",
        *,
        expiry: str | None = None,
        notify: bool = False,
    ) -> AnnouncementDict:
        """Create an announcement for a component."""
        payload: dict = {"message": message, "severity": severity, "notify": notify}
        if expiry:
            payload["expiry"] = expiry
        return self._post(
            f"/components/{project}/{component}/announcements/", json=payload
        ).json()

    def delete_component_announcement(
        self, project: str, component: str, announcement_id: int
    ) -> None:
        """Delete an announcement from a component."""
        self._delete(f"/components/{project}/{component}/announcements/{announcement_id}/")

    # ------------------------------------------------------------------
    # Translations
    # ------------------------------------------------------------------

    def list_translations(self, **filters: str) -> Iterator[TranslationDict]:
        """List all translations."""
        yield from self._paginate("/translations/", **filters)

    def get_translation(self, project: str, component: str, lang: str) -> TranslationDict:
        """Get translation details."""
        return self._get(f"/translations/{project}/{component}/{lang}/").json()

    def delete_translation(self, project: str, component: str, lang: str) -> None:
        """Delete a translation."""
        self._delete(f"/translations/{project}/{component}/{lang}/")

    def list_translation_units(
        self, project: str, component: str, lang: str, **filters: str
    ) -> Iterator[UnitDict]:
        """List translation units. Filter: q (search query)."""
        yield from self._paginate(f"/translations/{project}/{component}/{lang}/units/", **filters)

    def create_unit(
        self,
        project: str,
        component: str,
        lang: str,
        *,
        key: str = "",
        value: list[str] | None = None,
        context: str = "",
        source: list[str] | None = None,
        target: list[str] | None = None,
    ) -> UnitDict:
        """Create a new translation unit.

        For monolingual components, pass *key* and *value*.
        For bilingual components, pass *context*, *source*, and *target*.
        """
        payload: dict = {}
        if key:
            payload["key"] = key
            if value:
                payload["value"] = value
        else:
            if context:
                payload["context"] = context
            if source:
                payload["source"] = source
            if target:
                payload["target"] = target
        return self._post(
            f"/translations/{project}/{component}/{lang}/units/", json=payload
        ).json()

    def get_translation_statistics(self, project: str, component: str, lang: str) -> StatisticsDict:
        """Get translation statistics."""
        return self._get(f"/translations/{project}/{component}/{lang}/statistics/").json()

    def list_translation_changes(
        self, project: str, component: str, lang: str, **filters: str | int
    ) -> Iterator[ChangeDict]:
        """List changes for a translation."""
        yield from self._paginate(f"/translations/{project}/{component}/{lang}/changes/", **filters)

    def get_translation_repository(
        self, project: str, component: str, lang: str
    ) -> RepositoryDict:
        """Get VCS status for a translation."""
        return self._get(f"/translations/{project}/{component}/{lang}/repository/").json()

    def repo_translation(
        self,
        project: str,
        component: str,
        lang: str,
        operation: Literal["push", "pull", "commit", "reset", "cleanup"],
    ) -> RepoOperationResult:
        """Perform VCS operation on translation level."""
        return self._post(
            f"/translations/{project}/{component}/{lang}/repository/",
            json={"operation": operation},
        ).json()

    def autotranslate(
        self,
        project: str,
        component: str,
        lang: str,
        *,
        mode: str = "translate",
        filter_type: str = "all",
        auto_source: str = "mt",
        **extra: str | int,
    ) -> dict:
        """Trigger auto-translation.

        *mode*: 'suggest', 'translate', or 'fuzzy'.
        *filter_type*: 'all', 'nontranslated', 'todo', 'fuzzy', etc.
        *auto_source*: 'mt' (machine translation), 'tm' (translation memory), etc.
        """
        payload = {"mode": mode, "filter_type": filter_type, "auto_source": auto_source, **extra}
        return self._post(
            f"/translations/{project}/{component}/{lang}/autotranslate/", json=payload
        ).json()

    def list_translation_announcements(
        self, project: str, component: str, lang: str
    ) -> Iterator[AnnouncementDict]:
        """List announcements for a translation."""
        yield from self._paginate(f"/translations/{project}/{component}/{lang}/announcements/")

    # ------------------------------------------------------------------
    # Units
    # ------------------------------------------------------------------

    def list_units(self, **filters: str) -> Iterator[UnitDict]:
        """List all units (with optional search query q)."""
        yield from self._paginate("/units/", **filters)

    def get_unit(self, unit_id: int) -> UnitDict:
        """Get unit details."""
        return self._get(f"/units/{unit_id}/").json()

    def update_unit(
        self,
        unit_id: int,
        *,
        target: list[str] | None = None,
        state: int | None = None,
        fuzzy: bool | None = None,
        explanation: str | None = None,
        extra_flags: str | None = None,
        **extra: str | int | bool | list[str],
    ) -> UnitDict:
        """Partially update a unit (translate, change state, etc.)."""
        payload: dict = {}
        if target is not None:
            payload["target"] = target
        if state is not None:
            payload["state"] = state
        if fuzzy is not None:
            payload["fuzzy"] = fuzzy
        if explanation is not None:
            payload["explanation"] = explanation
        if extra_flags is not None:
            payload["extra_flags"] = extra_flags
        payload.update(extra)
        return self._patch(f"/units/{unit_id}/", json=payload).json()

    def put_unit(
        self,
        unit_id: int,
        *,
        target: list[str] | None = None,
        state: int | None = None,
    ) -> UnitDict:
        """Fully replace a unit."""
        payload: dict = {}
        if target is not None:
            payload["target"] = target
        if state is not None:
            payload["state"] = state
        return self._put(f"/units/{unit_id}/", json=payload).json()

    def delete_unit(self, unit_id: int) -> None:
        """Delete a unit."""
        self._delete(f"/units/{unit_id}/")

    def list_unit_translations(self, unit_id: int) -> list[UnitDict]:
        """List all target translation units for a source unit. (v5.11+)"""
        return self._get(f"/units/{unit_id}/translations/").json()

    def create_unit_comment(self, unit_id: int, comment: str) -> dict:
        """Add a comment to a unit. (v5.12+)"""
        return self._post(f"/units/{unit_id}/comments/", json={"comment": comment}).json()

    # ------------------------------------------------------------------
    # Changes
    # ------------------------------------------------------------------

    def list_changes(self, **filters: str | int) -> Iterator[ChangeDict]:
        """List all changes. Filters: user, action, timestamp_after, timestamp_before."""
        yield from self._paginate("/changes/", **filters)

    def get_change(self, change_id: int) -> ChangeDict:
        """Get change details."""
        return self._get(f"/changes/{change_id}/").json()

    # ------------------------------------------------------------------
    # Languages
    # ------------------------------------------------------------------

    def list_languages(self) -> Iterator[LanguageDict]:
        """List all languages."""
        yield from self._paginate("/languages/")

    def get_language(self, code: str) -> LanguageDict:
        """Get language details."""
        return self._get(f"/languages/{code}/").json()

    def create_language(
        self,
        code: str,
        name: str,
        direction: str = "ltr",
        *,
        population: int = 0,
        plural: PluralDict | None = None,
    ) -> LanguageDict:
        """Create a new language."""
        payload: dict = {
            "code": code,
            "name": name,
            "direction": direction,
            "population": population,
        }
        if plural:
            payload["plural"] = plural
        return self._post("/languages/", json=payload).json()

    def update_language(self, code: str, **fields: str | int | dict) -> LanguageDict:
        """Update language fields (PATCH)."""
        return self._patch(f"/languages/{code}/", json=fields).json()

    def delete_language(self, code: str) -> None:
        """Delete a language."""
        self._delete(f"/languages/{code}/")

    def get_language_statistics(self, code: str) -> StatisticsDict:
        """Get language statistics."""
        return self._get(f"/languages/{code}/statistics/").json()

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    def list_users(self, **filters: str | int) -> Iterator[UserDict]:
        """List users."""
        yield from self._paginate("/users/", **filters)

    def get_user(self, username: str) -> UserDict:
        """Get user details."""
        return self._get(f"/users/{username}/").json()

    def create_user(
        self,
        username: str,
        email: str,
        full_name: str,
        *,
        is_superuser: bool = False,
        is_active: bool = True,
        is_bot: bool = False,
    ) -> UserDict:
        """Create a new user. Requires user.edit permission."""
        return self._post(
            "/users/",
            json={
                "username": username,
                "email": email,
                "full_name": full_name,
                "is_superuser": is_superuser,
                "is_active": is_active,
                "is_bot": is_bot,
            },
        ).json()

    def update_user(self, username: str, **fields: str | bool) -> UserDict:
        """Update user fields (PATCH)."""
        return self._patch(f"/users/{username}/", json=fields).json()

    def delete_user(self, username: str) -> None:
        """Deactivate a user."""
        self._delete(f"/users/{username}/")

    def get_user_statistics(self, username: str) -> UserStatisticsDict:
        """Get user translation statistics."""
        return self._get(f"/users/{username}/statistics/").json()

    def get_user_contributions(self, username: str) -> ContributionDict:
        """Get user contributions."""
        return self._get(f"/users/{username}/contributions/").json()

    def add_user_group(self, username: str, group_id: str) -> None:
        """Add a user to a group."""
        self._post(f"/users/{username}/groups/", data={"group_id": group_id})

    def remove_user_group(self, username: str, group_id: str) -> None:
        """Remove a user from a group."""
        self._post(f"/users/{username}/groups/", data={"group_id": group_id})

    # ------------------------------------------------------------------
    # Groups
    # ------------------------------------------------------------------

    def list_groups(self) -> Iterator[GroupDict]:
        """List groups."""
        yield from self._paginate("/groups/")

    def get_group(self, group_id: int) -> GroupDict:
        """Get group details."""
        return self._get(f"/groups/{group_id}/").json()

    def create_group(
        self,
        name: str,
        *,
        project_selection: int = 0,
        language_selection: int = 0,
        defining_project: str = "",
    ) -> GroupDict:
        """Create a new group."""
        payload: dict = {
            "name": name,
            "project_selection": project_selection,
            "language_selection": language_selection,
        }
        if defining_project:
            payload["defining_project"] = defining_project
        return self._post("/groups/", json=payload).json()

    def update_group(self, group_id: int, **fields: str | int) -> GroupDict:
        """Update group fields (PATCH)."""
        return self._patch(f"/groups/{group_id}/", json=fields).json()

    def delete_group(self, group_id: int) -> None:
        """Delete a group."""
        self._delete(f"/groups/{group_id}/")

    def add_group_role(self, group_id: int, role_id: int) -> None:
        """Associate a role with a group."""
        self._post(f"/groups/{group_id}/roles/", data={"role_id": str(role_id)})

    def remove_group_role(self, group_id: int, role_id: int) -> None:
        """Remove a role from a group."""
        self._delete(f"/groups/{group_id}/roles/{role_id}")

    def add_group_project(self, group_id: int, project_id: int) -> None:
        """Associate a project with a group."""
        self._post(f"/groups/{group_id}/projects/", data={"project_id": str(project_id)})

    def remove_group_project(self, group_id: int, project_id: int) -> None:
        """Remove a project from a group."""
        self._delete(f"/groups/{group_id}/projects/{project_id}")

    def add_group_component(self, group_id: int, component_id: int) -> None:
        """Associate a component with a group."""
        self._post(f"/groups/{group_id}/components/", data={"component_id": str(component_id)})

    def remove_group_component(self, group_id: int, component_id: int) -> None:
        """Remove a component from a group."""
        self._delete(f"/groups/{group_id}/components/{component_id}")

    def add_group_language(self, group_id: int, language_code: str) -> None:
        """Associate a language with a group."""
        self._post(f"/groups/{group_id}/languages/", data={"language_code": language_code})

    def remove_group_language(self, group_id: int, language_code: str) -> None:
        """Remove a language from a group."""
        self._delete(f"/groups/{group_id}/languages/{language_code}")

    def add_group_component_list(self, group_id: int, component_list_id: str) -> None:
        """Associate a component list with a group."""
        self._post(f"/groups/{group_id}/componentlists/", data={"component_list_id": component_list_id})

    def remove_group_component_list(self, group_id: int, component_list_id: int) -> None:
        """Remove a component list from a group."""
        self._delete(f"/groups/{group_id}/componentlists/{component_list_id}")

    def add_group_admin(self, group_id: int, user_id: str) -> None:
        """Add a team admin to a group. (v5.5+)"""
        self._post(f"/groups/{group_id}/admins/", data={"user_id": user_id})

    def remove_group_admin(self, group_id: int, user_id: int) -> None:
        """Remove a team admin from a group. (v5.5+)"""
        self._delete(f"/groups/{group_id}/admins/{user_id}")

    # ------------------------------------------------------------------
    # Roles
    # ------------------------------------------------------------------

    def list_roles(self) -> Iterator[RoleDict]:
        """List all roles."""
        yield from self._paginate("/roles/")

    def get_role(self, role_id: int) -> RoleDict:
        """Get role details."""
        return self._get(f"/roles/{role_id}/").json()

    def create_role(self, name: str, permissions: list[str]) -> RoleDict:
        """Create a new role."""
        return self._post("/roles/", json={"name": name, "permissions": permissions}).json()

    def update_role(self, role_id: int, **fields: str | list[str]) -> RoleDict:
        """Update role fields (PATCH)."""
        return self._patch(f"/roles/{role_id}/", json=fields).json()

    def delete_role(self, role_id: int) -> None:
        """Delete a role."""
        self._delete(f"/roles/{role_id}/")

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------

    def download_file(
        self,
        project: str,
        component: str,
        lang: str,
        *,
        format: str = "po",
    ) -> bytes:
        """Download a translation file."""
        return self._get(
            f"/translations/{project}/{component}/{lang}/file/", format=format
        ).content

    def upload_file(
        self,
        project: str,
        component: str,
        lang: str,
        filepath: str,
        *,
        method: str = "translate",
        conflicts: str = "ignore",
    ) -> dict:
        """Upload a translation file.

        *method*: 'translate', 'add', 'suggest', 'fuzzy', 'replace'.
        *conflicts*: 'ignore', 'replace-translated', 'replace-approved'.
        """
        _name, fh, mime = _file_handle(filepath)
        try:
            return self._post(
                f"/translations/{project}/{component}/{lang}/file/",
                files={"file": (_name, fh, mime)},
                data={"method": method, "conflicts": conflicts},
            ).json()
        finally:
            fh.close()

    def download_project_language_file(
        self,
        project: str,
        language_code: str,
        *,
        format: str = "po",
        filter: str = "",
    ) -> bytes:
        """Download project files for a specific language."""
        params: dict[str, str] = {"format": format, "language_code": language_code}
        if filter:
            params["filter"] = filter
        return self._get(f"/projects/{project}/languages/{language_code}/file/", **params).content

    # ------------------------------------------------------------------
    # Screenshots
    # ------------------------------------------------------------------

    def list_screenshots(self) -> Iterator[ScreenshotDict]:
        """List all screenshots."""
        yield from self._paginate("/screenshots/")

    def get_screenshot(self, screenshot_id: int) -> ScreenshotDict:
        """Get screenshot details."""
        return self._get(f"/screenshots/{screenshot_id}/").json()

    def create_screenshot(
        self,
        name: str,
        project_slug: str,
        component_slug: str,
        language_code: str,
        filepath: str,
        *,
        repository_filename: str = "",
    ) -> ScreenshotDict:
        """Create a new screenshot."""
        _name, fh, mime = _file_handle(filepath)
        data: dict[str, str] = {
            "name": name,
            "project_slug": project_slug,
            "component_slug": component_slug,
            "language_code": language_code,
        }
        if repository_filename:
            data["repository_filename"] = repository_filename
        try:
            return self._post(
                "/screenshots/",
                files={"image": (_name, fh, mime)},
                data=data,
            ).json()
        finally:
            fh.close()

    def update_screenshot(self, screenshot_id: int, **fields: str) -> ScreenshotDict:
        """Update screenshot fields (PATCH)."""
        return self._patch(f"/screenshots/{screenshot_id}/", json=fields).json()

    def delete_screenshot(self, screenshot_id: int) -> None:
        """Delete a screenshot."""
        self._delete(f"/screenshots/{screenshot_id}/")

    def download_screenshot_file(self, screenshot_id: int) -> bytes:
        """Download screenshot image."""
        return self._get(f"/screenshots/{screenshot_id}/file/").content

    def upload_screenshot_file(self, screenshot_id: int, filepath: str) -> dict:
        """Replace screenshot image."""
        _name, fh, mime = _file_handle(filepath)
        try:
            return self._post(
                f"/screenshots/{screenshot_id}/file/",
                files={"image": (_name, fh, mime)},
            ).json()
        finally:
            fh.close()

    def add_screenshot_unit(self, screenshot_id: int, unit_id: int) -> dict:
        """Associate a source string with a screenshot."""
        return self._post(
            f"/screenshots/{screenshot_id}/units/",
            data={"unit_id": str(unit_id)},
        ).json()

    def remove_screenshot_unit(self, screenshot_id: int, unit_id: int) -> None:
        """Remove source string association from screenshot."""
        self._delete(f"/screenshots/{screenshot_id}/units/{unit_id}")

    # ------------------------------------------------------------------
    # Addons
    # ------------------------------------------------------------------

    def list_addons(self) -> Iterator[AddonDict]:
        """List all add-ons."""
        yield from self._paginate("/addons/")

    def get_addon(self, addon_id: int) -> AddonDict:
        """Get add-on details."""
        return self._get(f"/addons/{addon_id}/").json()

    def create_addon(
        self,
        project: str,
        component: str,
        name: str,
        configuration: dict | None = None,
    ) -> AddonDict:
        """Create an add-on for a component."""
        payload: dict = {"name": name}
        if configuration:
            payload["configuration"] = configuration
        return self._post(
            f"/components/{project}/{component}/addons/", json=payload
        ).json()

    def update_addon(self, addon_id: int, *, configuration: dict | None = None) -> AddonDict:
        """Update add-on configuration (PATCH)."""
        payload: dict = {}
        if configuration is not None:
            payload["configuration"] = configuration
        return self._patch(f"/addons/{addon_id}/", json=payload).json()

    def delete_addon(self, addon_id: int) -> None:
        """Delete an add-on."""
        self._delete(f"/addons/{addon_id}/")

    def trigger_addon(self, addon_id: int) -> dict:
        """Manually trigger an add-on run. (v5.17.1+)"""
        return self._post(f"/addons/{addon_id}/trigger/").json()

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------

    def list_categories(self) -> Iterator[CategoryDict]:
        """List all categories."""
        yield from self._paginate("/categories/")

    def get_category(self, category_id: int) -> CategoryDict:
        """Get category details."""
        return self._get(f"/categories/{category_id}/").json()

    def create_category(self, name: str, slug: str, project: str) -> CategoryDict:
        """Create a new category."""
        return self._post(
            "/categories/", json={"name": name, "slug": slug, "project": project}
        ).json()

    def update_category(self, category_id: int, **fields: str) -> CategoryDict:
        """Update category fields (PATCH)."""
        return self._patch(f"/categories/{category_id}/", json=fields).json()

    def delete_category(self, category_id: int) -> None:
        """Delete a category."""
        self._delete(f"/categories/{category_id}/")

    def get_category_statistics(self, category_id: int) -> StatisticsDict:
        """Get category statistics. (v5.5+)"""
        return self._get(f"/categories/{category_id}/statistics/").json()

    def list_category_announcements(self, category_id: int) -> Iterator[AnnouncementDict]:
        """List announcements for a category. (v5.17.1+)"""
        yield from self._paginate(f"/categories/{category_id}/announcements/")

    def create_category_announcement(
        self,
        category_id: int,
        message: str,
        severity: str = "info",
        *,
        expiry: str | None = None,
        notify: bool = False,
    ) -> AnnouncementDict:
        """Create an announcement for a category. (v5.17.1+)"""
        payload: dict = {"message": message, "severity": severity, "notify": notify}
        if expiry:
            payload["expiry"] = expiry
        return self._post(f"/categories/{category_id}/announcements/", json=payload).json()

    def delete_category_announcement(self, category_id: int, announcement_id: int) -> None:
        """Delete an announcement from a category. (v5.17.1+)"""
        self._delete(f"/categories/{category_id}/announcements/{announcement_id}/")

    # ------------------------------------------------------------------
    # Component Lists
    # ------------------------------------------------------------------

    def list_component_lists(self) -> Iterator[ComponentListDict]:
        """List all component lists."""
        yield from self._paginate("/component-lists/")

    def get_component_list(self, slug: str) -> ComponentListDict:
        """Get component list details."""
        return self._get(f"/component-lists/{slug}/").json()

    def update_component_list(self, slug: str, **fields: str | bool) -> ComponentListDict:
        """Update component list fields (PATCH)."""
        return self._patch(f"/component-lists/{slug}/", json=fields).json()

    def delete_component_list(self, slug: str) -> None:
        """Delete a component list."""
        self._delete(f"/component-lists/{slug}/")

    def list_component_list_components(self, slug: str) -> Iterator[ComponentDict]:
        """List components in a component list. (v5.0.1+)"""
        yield from self._paginate(f"/component-lists/{slug}/components/")

    def add_to_component_list(self, slug: str, component_id: int) -> None:
        """Add a component to a component list."""
        self._post(
            f"/component-lists/{slug}/components/",
            data={"component_id": str(component_id)},
        )

    def remove_from_component_list(self, slug: str, component_slug: str) -> None:
        """Remove a component from a component list."""
        self._delete(f"/component-lists/{slug}/components/{component_slug}")

    # ------------------------------------------------------------------
    # Memory (Translation Memory)
    # ------------------------------------------------------------------

    def list_memory(
        self,
        *,
        source: str = "",
        source_language: str = "",
        target_language: str = "",
        project: str = "",
    ) -> Iterator[MemoryDict]:
        """List/search translation memory entries."""
        params: dict[str, str] = {}
        if source:
            params["source"] = source
        if source_language:
            params["source_language"] = source_language
        if target_language:
            params["target_language"] = target_language
        if project:
            params["project"] = project
        yield from self._paginate("/memory/", **params)

    def get_memory(self, memory_id: int) -> MemoryDict:
        """Get a translation memory entry."""
        return self._get(f"/memory/{memory_id}/").json()

    def delete_memory(self, memory_id: int) -> None:
        """Delete a translation memory entry."""
        self._delete(f"/memory/{memory_id}/")

    def lookup_memory(
        self,
        strings: list[str],
        source_language: str,
        target_language: str,
        *,
        project: str = "",
    ) -> MemoryLookupResult:
        """Look up translation memory matches for source strings."""
        payload: dict = {"strings": strings}
        return self._post(
            "/memory/lookup/",
            json=payload,
            source_language=source_language,
            target_language=target_language,
            project=project,
        ).json()

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    def get_task(self, task_uuid: str) -> TaskDict:
        """Get background task status."""
        return self._get(f"/tasks/{task_uuid}/").json()

    def get_task_output(self, task_uuid: str) -> str:
        """Get background task output."""
        return self._get(f"/tasks/{task_uuid}/output/").text

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def get_metrics(self) -> MetricsDict:
        """Get server metrics."""
        return self._get("/metrics/").json()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, q: str) -> list[dict]:
        """Site-wide search. Returns list of {name, url, category}."""
        return self._get("/search/", q=q).json()

    # ------------------------------------------------------------------
    # Exports
    # ------------------------------------------------------------------

    def get_rss(self, project: str = "", component: str = "") -> bytes:
        """Get RSS feed of changes. Optionally scoped to project/component."""
        if component:
            path = f"{self.base_url}/exports/rss/{project}/{component}/"
        elif project:
            path = f"{self.base_url}/exports/rss/{project}/"
        else:
            path = f"{self.base_url}/exports/rss/"
        return self._sess.get(path, timeout=self.timeout).content

    def get_export_stats(self, project: str, component: str, lang: str) -> dict:
        """Get JSON export of translation statistics."""
        return self._sess.get(
            f"{self.base_url}/exports/{project}/{component}/{lang}/",
            timeout=self.timeout,
        ).json()
