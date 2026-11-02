"""
网页正文抓取与清洗服务单元测试 (Scraper Service Unit Tests)
"""

from __future__ import annotations

import pytest

from app.services.scraper_service import (
    ScraperError,
    compute_reading_stats,
    parse_html_content,
)


def test_parse_html_content_extracts_title_author_and_clean_body():
    sample_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>系统思维与长期主义 - 深度专栏</title>
        <meta name="author" content="张明远" />
        <meta property="og:site_name" content="思想实验室" />
    </head>
    <body>
        <nav>首页 | 订阅 | 登录</nav>
        <article>
            <h1>系统思维与长期主义</h1>
            <p>在复杂系统中，原因和结果往往在时空上相距甚远，直觉常常失效。</p>
            <p>许多组织之所以陷入局部最优陷阱，关键在于只关注短期可见指标，而忽视了正负反馈回路的延迟效应。</p>
            <blockquote>真正的战略定力，来源于对底层结构而非表象波动的深刻洞察。</blockquote>
        </article>
        <footer>版权所有 2026</footer>
        <script>console.log("tracking");</script>
    </body>
    </html>
    """
    extracted = parse_html_content(sample_html, url="https://blog.example.com/systems-thinking")
    assert extracted.title == "系统思维与长期主义"
    assert extracted.author == "张明远"
    assert extracted.site_name == "思想实验室"
    assert "反馈回路" in extracted.content
    assert "tracking" not in extracted.content
    assert extracted.word_count > 40
    assert extracted.reading_time_minutes >= 1


def test_parse_empty_html_raises_scraper_error():
    with pytest.raises(ScraperError):
        parse_html_content("   ", url="https://example.com")


def test_compute_reading_stats_mixed_chinese_and_english():
    text = "深度阅读 Deep Reading 是构建 Personal Knowledge Base 的核心能力。" * 25
    word_count, minutes = compute_reading_stats(text)
    assert word_count > 350
    assert minutes >= 2
