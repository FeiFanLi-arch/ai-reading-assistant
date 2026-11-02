"""
应用配置管理模块 (Application Configuration)

支持从环境变量 (.env) 加载初始配置，并提供清晰的默认值。
运行时可通过系统设置接口动态更新 AI 引擎参数（持久化在 SQLite AppSetting 表中）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# 加载项目根目录下的 .env 文件（若存在）
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass
class Config:
    """全局基础配置对象"""

    APP_ENV: str = os.getenv("APP_ENV", "development")
    APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT: int = int(os.getenv("APP_PORT", "8000"))
    SECRET_KEY: str = os.getenv("SECRET_KEY", "ai-reading-assistant-dev-secret-key")

    # 数据库配置：默认保存在项目根目录下的 data/reading_assistant.db
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(BASE_DIR / 'data' / 'reading_assistant.db').as_posix()}",
    )

    # AI 大模型配置 (兼容 OpenAI 接口标准)
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "auto")  # auto | openai | local
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "").strip()
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").strip()
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini").strip()
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    LLM_TIMEOUT_SECONDS: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))

    # 网页抓取配置
    SCRAPER_TIMEOUT_SECONDS: int = int(os.getenv("SCRAPER_TIMEOUT_SECONDS", "15"))
    SCRAPER_USER_AGENT: str = os.getenv(
        "SCRAPER_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    )

    # 是否自动注入首次启动演示数据
    SEED_DEMO_DATA: bool = os.getenv("SEED_DEMO_DATA", "true").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
