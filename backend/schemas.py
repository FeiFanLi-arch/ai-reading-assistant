"""Public API and model-response schemas."""

from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator


Identifier = Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")]


def valid_timestamp(value: str) -> str:
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("时间必须是有效的 ISO 8601 日期时间") from exc
    if stamp.tzinfo is None:
        raise ValueError("时间必须包含时区")
    return value


Timestamp = Annotated[str, Field(max_length=100), AfterValidator(valid_timestamp)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Argument(StrictModel):
    point: str = Field(min_length=1, max_length=3000)
    evidence: str = Field(min_length=1, max_length=4000)


class AuthorStance(StrictModel):
    position: str = Field(min_length=1, max_length=3000)
    tone: str = Field(min_length=1, max_length=1000)
    confidence: str = Field(min_length=1, max_length=1000)


class Summary(StrictModel):
    core_points: list[str] = Field(min_length=1, max_length=12)
    arguments: list[Argument] = Field(min_length=1, max_length=12)
    author_stance: AuthorStance
    insights: list[str] = Field(min_length=1, max_length=12)
    caveats: list[str] = Field(min_length=1, max_length=12)


class TopicInput(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("主题名称不能为空")
        return value.strip()


class ArticleInput(StrictModel):
    url: str | None = Field(default=None, max_length=2048)
    text: str | None = Field(default=None, max_length=100_000)
    title: str | None = Field(default=None, max_length=300)
    topic_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def exactly_one_source(self):
        self.url = self.url.strip() if self.url else None
        self.text = self.text.strip() if self.text else None
        if bool(self.url) == bool(self.text):
            raise ValueError("请提供文章链接或文本，且只提供其中一种")
        if self.text and len(self.text) < 20:
            raise ValueError("文章文本至少需要 20 个字符")
        return self


class ArticlePatch(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    topic_id: str | None = Field(default=None, max_length=100)
    favorite: bool | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("标题不能为空")
        return value.strip() if value else value


class QuestionInput(StrictModel):
    question: str = Field(min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def clean_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("问题不能为空")
        return value.strip()


class CompareInput(StrictModel):
    article_ids: list[str] | None = Field(default=None, min_length=2, max_length=10)


class Difference(StrictModel):
    article_id: str
    title: str
    position: str


class ComparisonResult(StrictModel):
    overview: str = Field(min_length=1, max_length=8000)
    common_ground: list[str] = Field(min_length=1, max_length=12)
    differences: list[Difference] = Field(min_length=2, max_length=10)
    contradictions: list[str] = Field(min_length=1, max_length=12)
    insights: list[str] = Field(min_length=1, max_length=12)


Mode = Literal["demo", "ai"]


class BackupTopic(TopicInput):
    id: Identifier
    created_at: Timestamp
    article_count: int | None = None


class BackupArticle(StrictModel):
    id: Identifier
    title: str = Field(min_length=1, max_length=300)
    url: str | None = Field(default=None, max_length=2048)
    text: str = Field(min_length=20, max_length=100_000)
    topic_id: Identifier | None = None
    favorite: bool = False
    created_at: Timestamp
    updated_at: Timestamp
    word_count: int
    summary: Summary | None = None
    mode: Mode = "demo"
    error: str | None = None

    @field_validator("url")
    @classmethod
    def safe_source_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if any(ord(character) < 33 for character in value) or "\\" in value:
            raise ValueError("备份文章链接包含无效字符")
        try:
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError("备份文章链接必须是完整的 http(s) URL")
            if parsed.username is not None or parsed.password is not None:
                raise ValueError("备份文章链接不能包含用户名或密码")
            parsed.hostname.encode("idna")
            if parsed.port is not None and parsed.port not in {80, 443}:
                raise ValueError("备份文章链接仅允许使用 80 或 443 端口")
        except (ValueError, UnicodeError) as exc:
            raise ValueError("备份文章链接无效；仅允许无凭据的完整 http(s) URL") from exc
        return value


class BackupMessage(StrictModel):
    id: Identifier
    article_id: Identifier
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=30_000)
    created_at: Timestamp
    mode: Mode = "demo"


class BackupComparison(StrictModel):
    id: Identifier
    topic_id: Identifier
    article_ids: list[Identifier] = Field(min_length=2, max_length=10)
    created_at: Timestamp
    mode: Mode = "demo"
    result: ComparisonResult


class Backup(StrictModel):
    version: Literal[1]
    exported_at: str | None = None
    topics: list[BackupTopic] = Field(max_length=2000)
    articles: list[BackupArticle] = Field(max_length=5000)
    messages: list[BackupMessage] = Field(max_length=20_000)
    comparisons: list[BackupComparison] = Field(max_length=5000)
