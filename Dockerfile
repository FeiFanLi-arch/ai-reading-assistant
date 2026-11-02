FROM python:3.12-slim

LABEL maintainer="AI Reading Assistant Team"
LABEL description="Personal AI Reading Assistant - Structured Summary, Critical Q&A, and Multi-Article Topic Synthesis"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000

WORKDIR /app

# 安装基础依赖与健康检查工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖声明以利用 Docker 缓存层
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# 复制项目代码
COPY . .

# 创建持久化数据目录
RUN mkdir -p /app/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/system/health || exit 1

# 使用 Gunicorn 启动生产级 WSGI 服务（多线程支持并发 AI 请求）
CMD ["gunicorn", "-w", "2", "--threads", "4", "-b", "0.0.0.0:8000", "--timeout", "120", "run:app"]
