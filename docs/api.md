# HTTP API

服务与前端同源。以下路径以 `/api` 为前缀，正文和响应为 JSON。`/health` 返回 `{"status":"ok"}`。交互式 OpenAPI 位于 `/docs`。

配置 `APP_ACCESS_TOKEN` 时，API、`/docs`、`/redoc` 与 `/openapi.json` 需要 `X-Access-Token: <口令>` 或 `Authorization: Bearer <口令>`。浏览器设置使用前一种。携带 `Origin` 的写入请求必须与当前请求的来源一致。通过反向代理部署时，应正确传递主机与协议。

## 配置

`GET /api/config`

```json
{"mode":"demo","model":"本地规则摘录","max_text_length":100000}
```

不会返回模型密钥、访问口令或完整服务端配置。

## 主题

| 方法与路径 | 正文 / 行为 | 成功响应 |
| --- | --- | --- |
| `GET /api/topics` | 按创建时间倒序 | `Topic[]` |
| `POST /api/topics` | `{name, description?}` | `201 Topic` |
| `PATCH /api/topics/{id}` | `{name, description?}` | `Topic` |
| `DELETE /api/topics/{id}` | 删除主题和其对比历史；文章解除主题关联 | `204` |

`Topic` 包含 `id`、`name`、`description`、`created_at`、`article_count`。名称去除首尾空白后不能为空，最多 80 字符，大小写不敏感唯一；说明最多 500 字符。更新需要提供名称。

## 文章

| 方法与路径 | 正文 / 参数 | 成功响应 |
| --- | --- | --- |
| `GET /api/articles` | `q`、`topic_id`、`favorite`、`limit`、`offset` | `{items: Article[], total}` |
| `POST /api/articles` | `{url?, text?, title?, topic_id?}` | `201 Article` |
| `GET /api/articles/{id}` | 文章详情 | `Article` |
| `PATCH /api/articles/{id}` | `{title?, topic_id?: string\|null, favorite?: boolean}` | `Article` |
| `DELETE /api/articles/{id}` | 同时删除其对话和引用它的对比历史 | `204` |
| `POST /api/articles/{id}/summarize` | 无需正文 | `Article` |

`url` 和 `text` 必须且只能提供一个。文本去除首尾空白后最少 20 字符，最多 100000 字符；标题最多 300 字符。链接最多 2048 字符，仅支持公网 HTTP(S) 的 80 / 443 端口。

列表按 `updated_at` 倒序；新增、修改、摘要和追问会更新活动时间。`GET` 不修改文章。`q` 搜索标题和正文，最多 300 字符，`%`、`_` 按字面字符处理。`limit` 默认 50、范围 1—200；`offset` 默认 0。收藏过滤用 `favorite=true`。

`Article` 示例：

```json
{
  "id":"服务器生成的ID",
  "title":"主动阅读",
  "url":null,
  "text":"第一段正文。\n\n第二段正文。",
  "topic_id":null,
  "favorite":false,
  "created_at":"2026-10-30T00:00:00+00:00",
  "updated_at":"2026-10-30T00:00:00+00:00",
  "word_count":16,
  "summary":{
    "core_points":["核心主张 [p1]"],
    "arguments":[{"point":"论据解释","evidence":"原文依据 [p2]"}],
    "author_stance":{"position":"作者立场","tone":"语气","confidence":"判断把握与依据"},
    "insights":["可执行的行动"],
    "caveats":["证据局限或读取范围限制"]
  },
  "mode":"demo",
  "error":null
}
```

`word_count` 是中文字符与英文词的近似计数，不是模型 token 数。段落按空行切分，编号从 `[p1]` 开始。

**模型失败的保存语义**：文章先保存再生成摘要。生成失败仍返回已保存的 `Article`，其中 `error` 为可显示的错误信息，首次失败时 `summary=null`；重新生成失败时保留之前成功的摘要及其 `mode`。前端应检查 `error`，允许用户重试，不能仅凭 HTTP 201 / 200 认定摘要成功。

## 追问

`GET /api/articles/{id}/messages` 按时间正序返回 `Message[]`。

`POST /api/articles/{id}/messages`

```json
{"question":"这个观点有什么漏洞？"}
```

问题最多 2000 字符且不能全为空白。成功为 `201 {user: Message, assistant: Message}`。`Message` 包含 `id`、`article_id`、`role`（`user` / `assistant`）、`content`、`created_at`、`mode`。模型失败返回 `502`，不会只保存一半对话。

真实 AI 使用正文上下文和最多最近 12 条、总计约 16000 字符的历史消息。正文超过约 32000 字符输入预算时只提供开头节选，回答或摘要会注明范围限制。数据库仍保存完整正文和全部对话。

## 主题对比

`POST /api/topics/{id}/compare`

```json
{"article_ids":["第一篇ID","第二篇ID"]}
```

必须选择 2—10 篇不同文章，且全部属于该主题。省略 `article_ids` 时选择主题下所有文章，也受 2—10 篇限制。成功为 `201 Comparison`。

`GET /api/topics/{id}/comparisons` 按创建时间倒序返回历史 `Comparison[]`。

```json
{
  "id":"对比ID",
  "topic_id":"主题ID",
  "article_ids":["第一篇ID","第二篇ID"],
  "created_at":"2026-10-30T00:00:00+00:00",
  "mode":"demo",
  "result":{
    "overview":"总体总结",
    "common_ground":["共识"],
    "differences":[
      {"article_id":"第一篇ID","title":"第一篇","position":"观点与依据"},
      {"article_id":"第二篇ID","title":"第二篇","position":"观点与依据"}
    ],
    "contradictions":["冲突或无法确认的地方"],
    "insights":["综合洞察"]
  }
}
```

真实 AI 的对比正文预算在文章间分配；超出时在结果中注明仅分析节选。

## 数据备份

`GET /api/export` 返回整个工作区：

```json
{"version":1,"exported_at":"UTC时间","topics":[],"articles":[],"messages":[],"comparisons":[]}
```

将该对象原样作为 `POST /api/import` 的 JSON 正文导入。请求体最多 20 MB。导入采用原子合并：

- 相同表中已存在的 ID 跳过，**不会覆盖本地记录**。
- 同一个备份内的重复 ID、无效关联或不符合结构的数据拒绝导入。
- 实体及关联 ID 仅接受字母、数字、下划线与连字符；记录时间必须是带时区的 ISO 8601 时间。文章来源链接必须为不含用户名密码的 HTTP(S) URL，端口仅允许 80 / 443。
- 相同主题名称对应不同 ID 等约束冲突时，整次导入回滚。
- `version` 必须为 `1`，不支持任意未知字段。

成功返回：

```json
{"imported":{"topics":1,"articles":2,"messages":2,"comparisons":1},"skipped":0}
```

导入前建议另存当前工作区备份。导出包含私人原文和对话，不含服务端密钥。

## 错误

统一可显示错误形状为 `{"detail":"原因"}`。

| 状态 | 含义 |
| --- | --- |
| `401` | 缺失或无效的工作区访问口令 |
| `403` | 不允许的跨站写入 |
| `404` | 文章或主题不存在 |
| `409` | 名称 / 数据冲突，或生成期间文章关联发生变化 |
| `413` | 请求体超过 20 MB |
| `422` | 参数、网页提取或备份校验失败 |
| `502` | 模型不可用、认证失败、限流、超时或结构不兼容 |

摘要生成错误见上文的 `Article.error` 特殊语义。删除接口成功没有 JSON 正文。

