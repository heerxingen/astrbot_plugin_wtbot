"""TypedDict definitions for Weblate API response objects."""

from typing import TypedDict


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

class PaginatedResponse(TypedDict, total=False):
    count: int
    next: str | None
    previous: str | None
    results: list


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

class ProjectDict(TypedDict, total=False):
    name: str
    slug: str
    web: str
    translation_review: bool
    source_review: bool
    set_language_team: bool
    enable_hooks: bool
    instructions: str
    language_aliases: str
    components_list_url: str
    repository_url: str
    changes_list_url: str
    credits_url: str
    announcements_url: str
    url: str
    web_url: str


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------

class ComponentDict(TypedDict, total=False):
    project: dict
    name: str
    slug: str
    vcs: str
    linked_component: str
    repo: str
    git_export: str
    branch: str
    push: str
    push_branch: str
    filemask: str
    template: str
    edit_template: str
    intermediate: str
    new_base: str
    file_format: str
    file_format_params: dict
    license: str
    license_url: str
    agreement: str
    new_lang: str
    language_code_style: str
    source_language: dict
    check_flags: str
    priority: str
    enforced_checks: str
    restricted: str
    repoweb: str
    report_source_bugs: str
    merge_style: str
    commit_message: str
    add_message: str
    delete_message: str
    merge_message: str
    addon_message: str
    pull_message: str
    allow_translation_propagation: str
    enable_suggestions: str
    suggestion_voting: str
    suggestion_autoaccept: str
    push_on_commit: bool
    locked: bool
    commit_pending_age: int
    auto_lock_error: bool
    language_regex: str
    variant_regex: str
    is_glossary: bool
    glossary_color: str
    repository_url: str
    translations_url: str
    lock_url: str
    changes_list_url: str
    task_url: str
    credits_url: str
    announcements_url: str
    url: str
    web_url: str


# ---------------------------------------------------------------------------
# Translations
# ---------------------------------------------------------------------------

class TranslationDict(TypedDict, total=False):
    component: dict
    filename: str
    language: dict
    language_code: str
    is_template: bool
    is_source: bool
    total: int
    total_words: int
    translated: int
    translated_percent: float
    translated_words: int
    fuzzy: int
    fuzzy_percent: float
    fuzzy_words: int
    failing_checks: int
    failing_checks_percent: float
    failing_checks_words: int
    have_comment: int
    have_suggestion: int
    last_author: str | None
    last_change: str | None
    revision: str
    share_url: str
    translate_url: str
    repository_url: str
    file_url: str
    changes_list_url: str
    units_list_url: str
    announcements_url: str
    url: str
    web_url: str


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------

class UnitDict(TypedDict, total=False):
    translation: str
    source: list[str]
    previous_source: str
    target: list[str]
    id_hash: str
    content_hash: str
    location: str
    context: str
    note: str
    flags: str
    labels: list[str]
    state: int
    fuzzy: bool
    translated: bool
    approved: bool
    position: int
    has_suggestion: bool
    has_comment: bool
    has_failing_check: bool
    num_words: int
    priority: int
    id: int
    web_url: str
    url: str
    explanation: str
    extra_flags: str
    source_unit: str
    pending: bool
    timestamp: str
    last_updated: str


# ---------------------------------------------------------------------------
# Changes
# ---------------------------------------------------------------------------

class ChangeDict(TypedDict, total=False):
    id: int
    unit: str | None
    component: str
    translation: str
    user: str | None
    author: str | None
    timestamp: str
    action: int
    action_name: str
    target: str
    old: str
    details: dict
    url: str


# ---------------------------------------------------------------------------
# Languages
# ---------------------------------------------------------------------------

class PluralDict(TypedDict):
    id: int
    source: int
    number: int
    formula: str
    type: int


class LanguageDict(TypedDict, total=False):
    code: str
    name: str
    direction: str
    population: int
    plural: PluralDict
    aliases: list[str]
    url: str
    web_url: str
    statistics_url: str


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class UserDict(TypedDict, total=False):
    username: str
    full_name: str
    email: str
    is_superuser: bool
    is_active: bool
    is_bot: bool
    date_joined: str
    last_login: str
    groups: list[str]
    languages: list[str]
    url: str
    contributions_url: str
    statistics_url: str


class UserStatisticsDict(TypedDict, total=False):
    translated: int
    suggested: int
    uploaded: int
    commented: int
    languages: int


class ContributionDict(TypedDict, total=False):
    translations: list[str]


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

class GroupDict(TypedDict, total=False):
    id: int
    name: str
    project_selection: int
    language_selection: int
    defining_project: str | None
    roles: list[str]
    projects: list[str]
    components: list[str]
    componentlists: list[str]
    admins: list[str]
    languages: list[str]
    componentlist: str
    url: str


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

class RoleDict(TypedDict, total=False):
    id: int
    name: str
    permissions: list[str]
    url: str


# ---------------------------------------------------------------------------
# Screenshots
# ---------------------------------------------------------------------------

class ScreenshotDict(TypedDict, total=False):
    name: str
    repository_filename: str
    translation: str
    file_url: str
    units: list[str]
    id: int
    url: str


# ---------------------------------------------------------------------------
# Addons
# ---------------------------------------------------------------------------

class AddonDict(TypedDict, total=False):
    id: int
    name: str
    component: str
    configuration: dict
    url: str


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

class CategoryDict(TypedDict, total=False):
    id: int
    name: str
    slug: str
    project: str
    category: str
    announcements_url: str
    url: str


# ---------------------------------------------------------------------------
# Component Lists
# ---------------------------------------------------------------------------

class ComponentListDict(TypedDict, total=False):
    name: str
    slug: str
    show_dashboard: bool
    components: list[str]
    auto_assign: list[dict]
    url: str


# ---------------------------------------------------------------------------
# Memory (Translation Memory)
# ---------------------------------------------------------------------------

class MemoryDict(TypedDict, total=False):
    id: int
    source_language: str
    target_language: str
    source: str
    target: str
    origin: str
    from_file: bool
    shared: bool
    url: str


class MemoryLookupResult(TypedDict, total=False):
    results: list[dict | None]


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class RepositoryDict(TypedDict, total=False):
    needs_commit: bool
    needs_merge: bool
    needs_push: bool
    remote_commit: str
    status: str
    merge_failure: str | None


class RepoOperationResult(TypedDict):
    result: bool


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

class StatisticsDict(TypedDict, total=False):
    total: int
    total_words: int
    total_chars: int
    last_change: str
    translated: int
    translated_percent: float
    translated_words: int
    translated_words_percent: float
    translated_chars: int
    translated_chars_percent: float
    fuzzy: int
    fuzzy_percent: float
    fuzzy_words: int
    fuzzy_words_percent: float
    fuzzy_chars: int
    fuzzy_chars_percent: float
    failing: int
    failing_percent: float
    approved: int
    approved_percent: float
    approved_words: int
    approved_words_percent: float
    approved_chars: int
    approved_chars_percent: float
    readonly: int
    readonly_percent: float
    readonly_words: int
    readonly_words_percent: float
    readonly_char_percent: float
    suggestions: int
    comments: int
    name: str
    url: str
    url_translate: str
    code: str


# ---------------------------------------------------------------------------
# Lock
# ---------------------------------------------------------------------------

class LockDict(TypedDict):
    locked: bool


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------

class LabelDict(TypedDict, total=False):
    id: int
    name: str
    color: str


# ---------------------------------------------------------------------------
# Announcements
# ---------------------------------------------------------------------------

class AnnouncementDict(TypedDict, total=False):
    id: int
    message: str
    severity: str
    expiry: str | None
    notify: bool


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

class TaskDict(TypedDict, total=False):
    uuid: str
    completed: bool
    progress: int
    result: dict
    log: str
    url: str


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

class MetricsDict(TypedDict, total=False):
    units: int
    units_translated: int
    users: int
    changes: int
    projects: int
    components: int
    translations: int
    languages: int
    checks: int
    configuration_errors: int
    suggestions: int
    celery_queues: dict
    name: str
    version: str


# ---------------------------------------------------------------------------
# Credits
# ---------------------------------------------------------------------------

class CreditDict(TypedDict, total=False):
    email: str
    full_name: str
    change_count: str


# ---------------------------------------------------------------------------
# Linked components
# ---------------------------------------------------------------------------

class LinkedComponentDict(TypedDict, total=False):
    projects: list[dict]
