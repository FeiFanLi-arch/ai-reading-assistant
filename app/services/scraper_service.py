"""
网页正文抓取与智能清洗服务 (Web Article Scraper & Readability Extractor)

支持：
1. 标准新闻、博客、公众号 (#js_content)、知乎专栏、Substack、Medium 等主流网页结构解析
2. 自动剔除导航栏、脚本、广告、页脚等噪音节点
3. 自动提取文章标题、作者、站点名称与段落化正文
4. 中英文混合字数统计与预计阅读时长计算
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from app.config import Config


class ScraperError(Exception):
    """网页抓取或正文解析失败异常"""
    pass


@dataclass
class ExtractedArticle:
    """抓取并清洗后的结构化文章结果"""
    title: str
    content: str
    url: str
    site_name: str
    author: str | None
    word_count: int
    reading_time_minutes: int


# 常见正文容器选择器（按优先级排序）
MAIN_CONTENT_SELECTORS = [
    "#js_content",                 # 微信公众号文章
    "article",                     # HTML5 语义化文章标签
    "[role='main']",               # WAI-ARIA 主内容区
    "main",                        # HTML5 主体标签
    ".post-content",
    ".article-content",
    ".entry-content",
    ".Post-RichTextContainer",     # 知乎专栏
    ".RichText",
    ".markdown-body",              # GitHub / 技术博客
    "#article-content",
    ".content-body",
    ".story-body",
]

# 需移除的噪音标签
NOISE_TAGS = [
    "script",
    "style",
    "noscript",
    "iframe",
    "svg",
    "canvas",
    "form",
    "button",
    "nav",
    "footer",
    "header",
    "aside",
]


def compute_reading_stats(text: str) -> tuple[int, int]:
    """
    计算中英文混合文本的字数与预计阅读时间（分钟）。
    中文按汉字计数，英文按单词计数；平均阅读速度按 350 字(词)/分钟估算。
    """
    if not text or not text.strip():
        return 0, 1
    cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    non_cjk_text = re.sub(r"[\u4e00-\u9fff]", " ", text)
    latin_words = len(re.findall(r"[A-Za-z0-9_]+", non_cjk_text))
    total_count = cjk_chars + latin_words
    if total_count == 0:
        total_count = len(text.strip())
    reading_minutes = max(1, math.ceil(total_count / 350))
    return total_count, reading_minutes


def clean_whitespace(text: str) -> str:
    """规范化多行文本中的空白字符，保留段落结构"""
    lines = []
    for raw_line in text.splitlines():
        cleaned = re.sub(r"[ \t\r\f\v]+", " ", raw_line).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n\n".join(lines)


def _extract_meta_content(soup: BeautifulSoup, selectors: list[tuple[str, str]]) -> str | None:
    """按属性候选列表提取 meta 标签内容"""
    for attr_name, attr_val in selectors:
        tag = soup.find("meta", attrs={attr_name: attr_val})
        if tag and isinstance(tag, Tag):
            content = (tag.get("content") or "").strip()
            if content:
                return content
    return None


def parse_html_content(html: str, url: str = "") -> ExtractedArticle:
    """
    从 HTML 源码中提取标题、作者、站点名与干净的正文段落。
    该函数不依赖网络请求，便于直接进行单元测试。
    """
    if not html or not html.strip():
        raise ScraperError("网页返回内容为空，无法解析正文。")

    soup = BeautifulSoup(html, "html.parser")

    # 1. 提取站点名称
    parsed_url = urlparse(url) if url else None
    domain = (parsed_url.netloc or "").replace("www.", "") if parsed_url else ""
    site_name = (
        _extract_meta_content(
            soup,
            [
                ("property", "og:site_name"),
                ("name", "application-name"),
                ("name", "twitter:site"),
            ],
        )
        or domain
        or "Web Article"
    )

    # 2. 提取作者信息
    author = _extract_meta_content(
        soup,
        [
            ("name", "author"),
            ("property", "article:author"),
            ("name", "twitter:creator"),
        ],
    )
    if not author:
        author_node = soup.select_one("[rel='author'], .author-name, .post-author, #js_name")
        if author_node:
            author = author_node.get_text(strip=True)[:80]

    # 3. 提取文章标题
    title = _extract_meta_content(
        soup,
        [
            ("property", "og:title"),
            ("name", "twitter:title"),
        ],
    )
    if not title:
        h1_node = soup.find("h1")
        if h1_node:
            title = h1_node.get_text(strip=True)
    if not title and soup.title and soup.title.string:
        title = soup.title.string.strip()
        # 去掉常见的站点后缀（如 " - 知乎" / " | 少数派"）
        title = re.split(r"\s+[-|_—]\s+", title)[0].strip()
    title = title or "未命名网页文章"

    # 4. 清理噪音标签
    for tag_name in NOISE_TAGS:
        for noisy in soup.find_all(tag_name):
            noisy.decompose()

    # 移除常见侧边栏/评论/推荐类名节点
    for noisy_selector in [
        ".sidebar",
        ".comments",
        "#comments",
        ".related-posts",
        ".advertisement",
        ".share-buttons",
        ".toc",
    ]:
        for node in soup.select(noisy_selector):
            node.decompose()

    # 5. 定位主内容节点
    main_container: Tag | None = None
    for selector in MAIN_CONTENT_SELECTORS:
        candidate = soup.select_one(selector)
        if candidate and len(candidate.get_text(strip=True)) >= 120:
            main_container = candidate
            break

    # 若未命中预设选择器，则按段落文本密度寻找最佳父容器
    if main_container is None:
        best_parent: Tag | None = None
        best_score = 0
        for p_node in soup.find_all(["p", "section"]):
            parent = p_node.parent
            if not isinstance(parent, Tag):
                continue
            text_len = len(parent.get_text(strip=True))
            if text_len > best_score:
                best_score = text_len
                best_parent = parent
        main_container = best_parent or soup.body or soup

    # 6. 结构化抽取段落与小标题
    paragraphs: list[str] = []
    seen_snippets: set[str] = set()

    if main_container:
        block_nodes = main_container.find_all(["h1", "h2", "h3", "h4", "p", "blockquote", "li", "pre"])
        if block_nodes:
            for node in block_nodes:
                text = node.get_text(" ", strip=True)
                if not text or len(text) < 4:
                    continue
                # 避免父子嵌套导致重复添加相同文本
                norm_key = text[:80]
                if norm_key in seen_snippets:
                    continue
                seen_snippets.add(norm_key)

                if node.name in ("h1", "h2", "h3", "h4"):
                    if text != title:
                        paragraphs.append(f"### {text}")
                elif node.name == "blockquote":
                    paragraphs.append(f"> {text}")
                elif node.name == "li":
                    paragraphs.append(f"- {text}")
                else:
                    paragraphs.append(text)

    content = "\n\n".join(paragraphs).strip()
    if len(content) < 80 and main_container:
        content = clean_whitespace(main_container.get_text("\n"))

    # 如果页面是纯 SPA 壳，尝试退化读取 meta description
    if len(content) < 40:
        meta_desc = _extract_meta_content(
            soup,
            [
                ("property", "og:description"),
                ("name", "description"),
            ],
        )
        if meta_desc and len(meta_desc) >= 20:
            content = meta_desc

    if not content or len(content.strip()) < 15:
        raise ScraperError(
            "未能从该链接提取到足够的正文内容（可能目标网站启用了反爬验证或纯前端动态渲染）。建议直接复制文章正文并粘贴导入。"
        )

    word_count, reading_minutes = compute_reading_stats(content)
    return ExtractedArticle(
        title=title[:300],
        content=content,
        url=url,
        site_name=site_name[:120],
        author=author[:120] if author else None,
        word_count=word_count,
        reading_time_minutes=reading_minutes,
    )


def fetch_url_article(url: str, timeout: int | None = None) -> ExtractedArticle:
    """
    通过 HTTP/HTTPS 抓取远程网页并解析出结构化文章正文。
    """
    cleaned_url = (url or "").strip()
    if not cleaned_url:
        raise ScraperError("文章链接不能为空。")

    parsed = urlparse(cleaned_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ScraperError("请输入合法的 HTTP / HTTPS 文章链接（例如 https://example.com/article）。")

    req_timeout = timeout or Config.SCRAPER_TIMEOUT_SECONDS
    headers = {
        "User-Agent": Config.SCRAPER_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    try:
        with httpx.Client(
            timeout=req_timeout,
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = client.get(cleaned_url)
            response.raise_for_status()
            html_text = response.text
    except httpx.HTTPStatusError as exc:
        raise ScraperError(
            f"目标网页返回错误状态码 (HTTP {exc.response.status_code})，无法直接抓取，请尝试直接复制正文粘贴。"
        ) from exc
    except httpx.RequestError as exc:
        raise ScraperError(
            f"无法连接到目标链接 ({exc.__class__.__name__})。若目标站点限制访问或当前处于离线环境，请直接粘贴文章文本。"
        ) from exc

    return parse_html_content(html_text, url=cleaned_url)
