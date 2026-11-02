# 交付验证记录

验证日期：2026-10-30。

## 已执行

- Windows / Python 3.12.7，按 `backend/requirements.txt` 安装直接依赖。
- `python -m pytest`：**77 passed**，2.57 秒。测试使用临时数据库；真实 AI 分支通过模拟服务响应验证，没有产生模型调用费用。
- 覆盖文章 / 对话持久化、主题对比、备份合并及失败回滚、输入边界、令牌与来源校验、模型结构与错误处理、SSRF / DNS 重绑定 / 重定向 / 网页体积限制。
- `node --check frontend/app.js`：通过。
- `docker compose config --quiet`：通过。
- 通过 Uvicorn 在本机启动，`/health` 返回 `{"status":"ok"}`。
- 实际 HTTP(S) 网页提取：公开示例页面成功提取正文，TLS 证书校验保持开启。
- 浏览器操作：示例导入、直接粘贴正文、结构化结果、建议问题与回复、段落引用跳转、创建主题、移动文章、选择两篇生成对比、刷新后恢复对话和对比、手机菜单与历史记录。
- 检查 1440 px 双栏布局及 390 px 手机布局；手机检查未见横向溢出，浏览器错误日志为空。

界面截图位于项目根目录 `preview.jpg`，显示本地演示模式的实际结果。

## 验证限制

- 当前环境安装了 Docker CLI，但 Docker 引擎未启动，因此本次没有实际构建或运行容器。仓库 CI 已包含镜像构建、容器健康检查与前端响应检查。
- 没有用户提供的模型密钥，未对外部模型执行真实付费请求。真实模型的摘要质量、特定服务商兼容性和额度需使用自己的配置验证。服务商必须支持 Chat Completions 与 JSON object 输出。
- 测试有一条 Starlette 对 AnyIO 类型别名的弃用警告，测试结果不受影响。

## 可复验命令

```sh
python -m pip install -r requirements-dev.txt
python -m pytest
node --check frontend/app.js  # 可选开发检查；运行应用不需要 Node.js
docker compose config --quiet
docker compose up --build -d
```

本文记录实际执行范围，不替代其他系统环境、网络和模型服务商的集成验证。
