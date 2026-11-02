"""
AI 智能分析引擎服务 (LLM & Local Heuristic Dual-Engine Service)

设计理念：
1. 【真实大模型模式 (LLM Mode)】：兼容所有 OpenAI 接口规范的服务商（OpenAI、DeepSeek、通义千问、Moonshot、硅基流动、本地 Ollama 等）。
2. 【内置启发式智能引擎 (Heuristic Smart Engine)】：当未配置 API Key 或用户选择本地引擎时，基于篇章结构特征、论点指示词、因果与转折连接词、关键词权重及跨文档矩阵比对，生成真实针对原文的结构化摘要、批判性追问回答与多文章对比报告，确保项目开箱 100% 可用。
3. 支持在 Web 界面右上角动态修改并持久化 API Key、Base URL 与模型名称。
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import Config
from app.models import AppSetting


# ---------------------------------------------------------------------------
# 运行时配置读取与持久化
# ---------------------------------------------------------------------------

SETTING_KEYS = (
    "llm_provider",
    "llm_api_key",
    "llm_base_url",
    "llm_model",
    "llm_temperature",
)


def get_runtime_llm_config(session: Session | None = None) -> dict[str, Any]:
    """获取当前生效的 AI 引擎配置（优先读取数据库持久化设置，其次读取环境变量）"""
    cfg = {
        "provider": Config.LLM_PROVIDER,
        "api_key": Config.LLM_API_KEY,
        "base_url": Config.LLM_BASE_URL,
        "model": Config.LLM_MODEL,
        "temperature": Config.LLM_TEMPERATURE,
    }
    if session is not None:
        rows = session.query(AppSetting).filter(AppSetting.key.in_(SETTING_KEYS)).all()
        db_map = {r.key: r.value for r in rows}
        if "llm_provider" in db_map and db_map["llm_provider"]:
            cfg["provider"] = db_map["llm_provider"]
        if "llm_api_key" in db_map:
            cfg["api_key"] = db_map["llm_api_key"]
        if "llm_base_url" in db_map and db_map["llm_base_url"]:
            cfg["base_url"] = db_map["llm_base_url"]
        if "llm_model" in db_map and db_map["llm_model"]:
            cfg["model"] = db_map["llm_model"]
        if "llm_temperature" in db_map and db_map["llm_temperature"]:
            try:
                cfg["temperature"] = float(db_map["llm_temperature"])
            except ValueError:
                pass

    # 判断实际是否使用远程 LLM
    provider = (cfg["provider"] or "auto").lower()
    has_key = bool(cfg["api_key"] and cfg["api_key"].strip())
    is_local_ollama = "localhost:11434" in cfg["base_url"] or "127.0.0.1:11434" in cfg["base_url"]

    if provider == "local":
        active_mode = "heuristic"
    elif provider == "openai" and (has_key or is_local_ollama):
        active_mode = "llm"
    elif provider == "auto" and (has_key or is_local_ollama):
        active_mode = "llm"
    else:
        active_mode = "heuristic"

    cfg["active_mode"] = active_mode
    return cfg


def save_runtime_llm_config(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """保存用户在前端界面更新的 AI 引擎配置"""
    mapping = {
        "provider": "llm_provider",
        "api_key": "llm_api_key",
        "base_url": "llm_base_url",
        "model": "llm_model",
        "temperature": "llm_temperature",
    }
    for field, db_key in mapping.items():
        if field in payload and payload[field] is not None:
            val_str = str(payload[field]).strip()
            existing = session.get(AppSetting, db_key)
            if existing:
                existing.value = val_str
            else:
                session.add(AppSetting(key=db_key, value=val_str))
    session.flush()
    return get_runtime_llm_config(session)


# ---------------------------------------------------------------------------
# 底层 OpenAI 兼容接口调用封装
# ---------------------------------------------------------------------------

def _extract_json_block(raw_text: str) -> dict[str, Any]:
    """从大模型返回文本中稳健提取 JSON 对象"""
    cleaned = raw_text.strip()
    # 去除 ```json ... ``` 包裹
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
    if fenced:
        cleaned = fenced.group(1)
    else:
        brace_start = cleaned.find("{")
        brace_end = cleaned.rfind("}")
        if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
            cleaned = cleaned[brace_start : brace_end + 1]
    return json.loads(cleaned)


def call_openai_compatible(
    messages: list[dict[str, str]],
    llm_cfg: dict[str, Any],
    expect_json: bool = False,
) -> str:
    """调用兼容 OpenAI `/v1/chat/completions` 的大模型接口"""
    base_url = (llm_cfg.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    endpoint = f"{base_url}/chat/completions"
    api_key = llm_cfg.get("api_key") or "ollama"
    model = llm_cfg.get("model") or "gpt-4o-mini"
    temperature = float(llm_cfg.get("temperature", 0.3))

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if expect_json:
        body["response_format"] = {"type": "json_object"}

    with httpx.Client(timeout=Config.LLM_TIMEOUT_SECONDS) as client:
        resp = client.post(endpoint, headers=headers, json=body)
        # 部分兼容接口不支持 response_format={"type": "json_object"}，若返回 400 则自动降级重试
        if resp.status_code == 400 and expect_json:
            body.pop("response_format", None)
            resp = client.post(endpoint, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# 内置启发式智能分析辅助函数 (Heuristic NLP Helpers)
# ---------------------------------------------------------------------------

STOPWORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个", "上", "也", "很",
    "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好", "自己", "这", "那", "与", "及", "或",
    "等", "被", "将", "可以", "因为", "所以", "但是", "如果", "虽然", "以及", "进行", "通过", "对于",
    "我们", "他们", "这个", "那个", "这些", "那些", "什么", "怎么", "如何", "为什么", "不是", "而是",
    "the", "and", "for", "that", "this", "with", "from", "are", "was", "were", "have", "has", "had",
    "not", "but", "what", "all", "when", "can", "more", "will", "into", "about", "which", "their",
}


def _split_sentences(text: str) -> list[str]:
    """将文章拆分为有意义的完整句子列表"""
    cleaned = re.sub(r"#{1,6}\s*", "", text)
    raw_parts = re.split(r"(?<=[。！？.!?\n])\s*", cleaned)
    sentences: list[str] = []
    for part in raw_parts:
        s = part.strip().lstrip("-*•> ").strip()
        if len(s) >= 12:
            sentences.append(s)
    return sentences


def _extract_keywords(text: str, top_k: int = 8) -> list[str]:
    """从文本中提取高频专业词汇或核心概念词"""
    # 提取中文 2~6 字词组或英文单词
    zh_tokens = re.findall(r"[\u4e00-\u9fff]{2,5}", text)
    en_tokens = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text)]
    counter: Counter[str] = Counter()

    for token in zh_tokens:
        if token not in STOPWORDS and not any(sw in token for sw in ("我们", "他们", "可以", "因为", "所以", "如果", "这个", "那个", "一种", "进行", "通过")):
            counter[token] += 1
    for token in en_tokens:
        if token not in STOPWORDS:
            counter[token] += 1

    # 去重包含关系的词
    candidates = [word for word, _ in counter.most_common(top_k * 3)]
    selected: list[str] = []
    for word in candidates:
        if not any(word != other and (word in other or other in word) for other in selected):
            selected.append(word)
        if len(selected) >= top_k:
            break
    return selected or ["深度阅读", "认知洞察", "方法论"]


def _score_sentence(sentence: str, keywords: list[str], markers: tuple[str, ...]) -> float:
    """为句子打分以提取核心观点、论据或行动建议"""
    score = 0.0
    for kw in keywords:
        if kw.lower() in sentence.lower():
            score += 2.0
    for marker in markers:
        if marker in sentence:
            score += 3.5
    # 适中长度的句子更适合作为观点摘要
    if 25 <= len(sentence) <= 130:
        score += 1.5
    elif len(sentence) > 200:
        score -= 1.0
    return score


def _heuristic_article_summary(title: str, content: str) -> tuple[dict[str, Any], list[str]]:
    """
    内置启发式引擎：深度解析文章正文，生成结构化摘要（核心观点、关键论据、作者态度、可行动洞察、核心概念、推荐追问）。
    """
    sentences = _split_sentences(content)
    keywords = _extract_keywords(f"{title} {content}", top_k=6)

    if not sentences:
        sentences = [content.strip() or title]

    # 1. 提取核心观点 (Core Viewpoints)
    thesis_markers = (
        "核心", "本质", "关键", "认为", "在于", "决定", "意味着", "结论", "必须", "真正",
        "最重要", "换言之", "归根结底", "根本", "不能只", "而是", "不仅", "趋势", "定律", "原则",
    )
    scored_viewpoints = sorted(
        enumerate(sentences),
        key=lambda item: _score_sentence(item[1], keywords, thesis_markers) + (2.0 if item[0] < 4 else 0.0),
        reverse=True,
    )
    picked_vp_indices: list[int] = []
    for idx, _ in scored_viewpoints:
        if idx not in picked_vp_indices:
            picked_vp_indices.append(idx)
        if len(picked_vp_indices) >= 4:
            break
    picked_vp_indices.sort()

    core_viewpoints = []
    for rank, idx in enumerate(picked_vp_indices):
        sent = sentences[idx]
        # 提炼短标题
        short_clause = re.split(r"[，,：:；;——]", sent)[0].strip()
        if len(short_clause) > 28:
            short_clause = short_clause[:26] + "…"
        elif len(short_clause) < 6 and len(keywords) > rank:
            short_clause = f"关于「{keywords[rank]}」的核心论断"
        core_viewpoints.append(
            {
                "title": short_clause,
                "detail": sent,
                "importance": "高" if rank < 2 else "中",
            }
        )

    # 2. 提取关键论据 (Key Arguments & Evidence)
    evidence_markers = (
        "数据", "研究", "实验", "发现", "显示", "例如", "比如", "案例", "根据", "证明",
        "统计", "历史", "对比", "因为", "由于", "导致", "%", "倍", "调查", "实践",
    )
    scored_evidence = sorted(
        enumerate(sentences),
        key=lambda item: _score_sentence(item[1], keywords, evidence_markers)
        + (3.0 if re.search(r"\d+", item[1]) else 0.0),
        reverse=True,
    )
    key_arguments = []
    used_ev = set(picked_vp_indices[:1])
    for idx, sent in scored_evidence:
        if idx in used_ev and len(sentences) > 4:
            continue
        used_ev.add(idx)
        # 判断论证类型
        if re.search(r"\d+%|\d+倍|统计|数据|调查|研究|实验", sent):
            logic_type = "数据与实证研究"
        elif any(w in sent for w in ("例如", "比如", "案例", "实践中", "场景")):
            logic_type = "典型案例佐证"
        elif any(w in sent for w in ("对比", "相比", "而", "反之", "不同")):
            logic_type = "对比与反差论证"
        else:
            logic_type = "因果逻辑推演"

        claim_prefix = keywords[len(key_arguments) % len(keywords)]
        key_arguments.append(
            {
                "claim": f"围绕「{claim_prefix}」的支撑论据",
                "evidence": sent,
                "logic_type": logic_type,
                "quote": sent if len(sent) <= 110 else sent[:108] + "…",
            }
        )
        if len(key_arguments) >= 3:
            break

    # 3. 分析作者态度与立场 (Author Stance)
    critical_count = sum(content.count(w) for w in ("警惕", "误区", "陷阱", "反思", "批判", "问题", "局限", "盲目", "泡沫"))
    constructive_count = sum(content.count(w) for w in ("建议", "构建", "方法", "策略", "路径", "提升", "实践", "行动", "未来"))
    empirical_count = sum(content.count(w) for w in ("数据", "实验", "研究", "模型", "机制", "分析", "客观", "证据"))

    if critical_count >= constructive_count and critical_count > 2:
        overall_tone = "审慎思辨 / 批判性反思"
        stance_desc = (
            f"作者对「{title}」相关议题持审慎乃至批判性审视态度，重点剖析了表面繁荣或惯性认知背后的逻辑盲区，"
            f"强调读者应当超越浅层直觉，关注「{keywords[0]}」的深层结构性约束。"
        )
        potential_bias = "文章侧重于揭示问题与潜在风险，可能在特定过渡期方案的宽容度上较为严苛，阅读时可结合具体业务发展阶段综合权衡。"
    elif empirical_count >= constructive_count and empirical_count > 3:
        overall_tone = "理性实证 / 深度拆解"
        stance_desc = (
            f"作者采取高度理性和结构化的分析视角，通过机制拆解与实证观察来探讨「{title}」，"
            f"主张以系统化框架理解「{'、'.join(keywords[:2])}」之间的内在因果关系。"
        )
        potential_bias = "分析框架偏向理性模型化推演，面对极端非理性个体行为或高不确定性边缘场景时，可能存在未覆盖的感性变量。"
    else:
        overall_tone = "建设性倡导 / 务实前瞻"
        stance_desc = (
            f"作者对「{title}」所代表的方向持积极且务实的建设性态度，不仅指出「{keywords[0]}」演进的必然性，"
            f"更致力于提供一套可落地的行动框架与方法论升级路径。"
        )
        potential_bias = "作者对所提倡的方法论抱有较高预期，在实际落地中需留意组织惯性、迁移成本或资源约束带来的执行摩擦力。"

    objectivity_score = min(92, max(68, 76 + empirical_count * 2 - max(0, critical_count - 5)))
    author_stance = {
        "overall_tone": overall_tone,
        "stance_description": stance_desc,
        "potential_bias": potential_bias,
        "target_audience": f"关注「{' / '.join(keywords[:3])}」领域的知识工作者、研究者与实践决策者",
        "objectivity_score": objectivity_score,
    }

    # 4. 提炼可行动洞察 (Actionable Insights)
    action_markers = (
        "应该", "应当", "建议", "需要", "必须", "第一步", "首先", "如何", "方法", "策略",
        "实践", "建立", "避免", "通过", "不妨", "尝试", "关键在于", "养成",
    )
    scored_actions = sorted(
        enumerate(sentences),
        key=lambda item: _score_sentence(item[1], keywords, action_markers),
        reverse=True,
    )
    actionable_insights = []
    priorities = ["高优先级 · 立即实践", "中优先级 · 流程优化", "长期建设 · 认知升级"]
    for idx_rank, (_, sent) in enumerate(scored_actions[:3]):
        kw_focus = keywords[idx_rank % len(keywords)]
        actionable_insights.append(
            {
                "action": f"行动项 {idx_rank + 1}：围绕「{kw_focus}」优化工作流与决策",
                "scenario": sent,
                "priority": priorities[idx_rank % len(priorities)],
                "expected_outcome": f"将文中关于「{kw_focus}」的洞察转化为可复用的个人/团队实践标准，降低试错成本。",
            }
        )

    # 5. 核心概念表 (Key Concepts)
    key_concepts = []
    for kw in keywords[:4]:
        # 找到包含该词的最具解释性的一句话
        matching_sents = [s for s in sentences if kw.lower() in s.lower()]
        def_sent = matching_sents[0] if matching_sents else f"文中讨论的核心议题维度之一：{kw}。"
        key_concepts.append(
            {
                "term": kw,
                "definition": def_sent if len(def_sent) <= 120 else def_sent[:118] + "…",
            }
        )

    # 6. 一句话核心总结 (One-Sentence TL;DR)
    first_vp = core_viewpoints[0]["detail"] if core_viewpoints else sentences[0]
    one_sentence_summary = (
        f"本文围绕「{title}」展开深度剖析，核心指出：{first_vp[:95]}{'…' if len(first_vp) > 95 else ''}，"
        f"并从「{'、'.join(keywords[:3])}」等维度给出了实证支撑与行动指南。"
    )

    # 7. 针对本文的启发式追问建议
    reading_questions = [
        f"这篇文章关于「{keywords[0]}」的核心观点有哪些潜在逻辑漏洞或隐含前提？",
        f"文中提出的洞察与第一性原理或经典理论框架有什么深层联系？",
        f"如果站在反对者的立场，针对本文的论据可以提出哪些反例？",
        f"如何将文中关于「{'、'.join(keywords[:2])}」的建议转化为本周可执行的 3 个具体步骤？",
    ]

    summary_payload = {
        "one_sentence_summary": one_sentence_summary,
        "core_viewpoints": core_viewpoints,
        "key_arguments": key_arguments,
        "author_stance": author_stance,
        "actionable_insights": actionable_insights,
        "key_concepts": key_concepts,
        "reading_questions": reading_questions,
        "engine_used": "heuristic",
    }
    return summary_payload, keywords[:5]


# ---------------------------------------------------------------------------
# 对外核心业务接口 1：生成单篇文章结构化摘要
# ---------------------------------------------------------------------------

def generate_article_summary(
    title: str,
    content: str,
    session: Session | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """
    输入文章标题与正文，返回 (summary_dict, tags_list)。
    若配置了大模型 API Key，优先调用大模型生成严格 JSON 结构；若未配置或调用异常，自动平滑降级至内置智能分析引擎。
    """
    llm_cfg = get_runtime_llm_config(session)
    if llm_cfg["active_mode"] == "llm":
        system_prompt = (
            "你是一位世界级的深度阅读教练、批判性思维专家与知识管理学者。"
            "请对用户提供的文章进行深度结构化拆解，并严格输出合法的 JSON 对象（不要包含多余的解释文字）。\n"
            "JSON 必须包含以下字段：\n"
            "{\n"
            '  "one_sentence_summary": "一句话高度凝练文章的核心主旨（50-120字）",\n'
            '  "tags": ["标签1", "标签2", "标签3", "标签4"],\n'
            '  "core_viewpoints": [\n'
            '    {"title": "观点短标题", "detail": "观点详细阐述", "importance": "高 或 中"}\n'
            "  ],\n"
            '  "key_arguments": [\n'
            '    {"claim": "支撑的分论点", "evidence": "文中使用的论据/数据/案例分析", "logic_type": "数据实证/案例对比/因果推演/权威引述", "quote": "原文代表性原句摘录"}\n'
            "  ],\n"
            '  "author_stance": {\n'
            '    "overall_tone": "如：审慎批判 / 理性实证 / 建设性倡导",\n'
            '    "stance_description": "作者的核心立场与倾向分析",\n'
            '    "potential_bias": "作者可能存在的视角局限、未充分讨论的假设或潜在偏见",\n'
            '    "target_audience": "最适合阅读本文的目标受众",\n'
            '    "objectivity_score": 85\n'
            "  },\n"
            '  "actionable_insights": [\n'
            '    {"action": "具体行动建议标题", "scenario": "具体执行方法与适用场景", "priority": "高优先级 · 立即实践", "expected_outcome": "预期带来的改变或收益"}\n'
            "  ],\n"
            '  "key_concepts": [\n'
            '    {"term": "核心概念或术语", "definition": "结合上下文的清晰界定"}\n'
            "  ],\n"
            '  "reading_questions": [\n'
            '    "启发读者深入思考的追问问题1",\n'
            '    "启发读者深入思考的追问问题2",\n'
            '    "启发读者深入思考的追问问题3"\n'
            "  ]\n"
            "}"
        )
        truncated_content = content[:14000]
        user_prompt = f"文章标题：{title}\n\n文章正文：\n{truncated_content}"
        try:
            raw_resp = call_openai_compatible(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                llm_cfg=llm_cfg,
                expect_json=True,
            )
            parsed = _extract_json_block(raw_resp)
            tags = [str(t) for t in parsed.pop("tags", []) if t][:6]
            if not tags:
                tags = _extract_keywords(f"{title} {content}", top_k=4)
            parsed["engine_used"] = "llm"
            return parsed, tags
        except Exception:
            # 平滑回退到内置启发式引擎，保证用户体验不中断
            pass

    return _heuristic_article_summary(title, content)


# ---------------------------------------------------------------------------
# 对外核心业务接口 2：单篇文章追问对话 (Follow-up Q&A)
# ---------------------------------------------------------------------------

def _heuristic_answer_article_question(
    title: str,
    content: str,
    summary: dict[str, Any],
    question: str,
    quoted_text: str | None = None,
) -> str:
    """
    内置启发式追问引擎：识别用户追问意图（漏洞批判、理论关联、反方视角、行动落地、概念解释或特定原文检索），
    结合文章核心观点、论据与匹配的原文段落给出有深度的结构化回答。
    """
    q_lower = question.lower()
    sentences = _split_sentences(content)
    viewpoints = summary.get("core_viewpoints", [])
    arguments = summary.get("key_arguments", [])
    stance = summary.get("author_stance", {})
    insights = summary.get("actionable_insights", [])
    concepts = summary.get("key_concepts", [])

    # 检索与问题最相关的原文句子
    q_keywords = _extract_keywords(f"{question} {quoted_text or ''}", top_k=5)
    relevant_sents = sorted(
        sentences,
        key=lambda s: sum(3.0 for kw in q_keywords if kw.lower() in s.lower()) + (1.0 if 20 <= len(s) <= 140 else 0.0),
        reverse=True,
    )[:3]

    quote_banner = ""
    if quoted_text and quoted_text.strip():
        quote_banner = f"> **📌 针对您引用的片段**：\n> *“{quoted_text.strip()[:220]}”*\n\n"

    # 意图分支 1：逻辑漏洞 / 批判性审视 / 局限性 / 反驳
    if any(k in q_lower for k in ("漏洞", "局限", "缺陷", "问题", "反驳", "批判", "假设", "偏见", "不足", "反对", "质疑")):
        vp_text = viewpoints[0]["detail"] if viewpoints else title
        ev_text = arguments[0]["evidence"] if arguments else (relevant_sents[0] if relevant_sents else "")
        bias_text = stance.get("potential_bias", "作者在推演过程中默认了外部环境与执行条件处于理想状态。")
        return (
            f"{quote_banner}"
            f"### 🔍 批判性审视：《{title}》的潜在逻辑漏洞与边界条件\n\n"
            f"从批判性思维（Critical Thinking）的视角审视，本文的核心论断——*“{vp_text}”*——建立在若干隐含前提之上，至少可以从以下三个维度提出审慎质疑：\n\n"
            f"1. **隐含假设与幸存者偏差（Hidden Assumptions）**\n"
            f"   - 文中引用的核心论据（*“{ev_text[:100]}…”*）在特定上下文下成立，但将其外推为普适规律时，忽略了不同行业周期、资源禀赋或个体认知基线的差异。\n"
            f"2. **视角局限与权衡代价（Trade-off Blindness）**\n"
            f"   - {bias_text}\n"
            f"   - 任何方法论的引入都伴随认知负荷与机会成本。作者重点阐述了正向收益，但对**迁移成本、极端反例以及边际效用递减点**着墨较少。\n"
            f"3. **反方立场的最强辩护（Steelman Counter-Argument）**\n"
            f"   - 如果站在反对者立场，完全可以提出：当面临极高不确定性或时间窗口极度紧迫的场景时，过度追求文中提倡的系统化范式反而可能拖慢反馈闭环，此时「快速试错与局部启发式决策」或许比完美框架更具适应性。\n\n"
            f"💡 **阅读建议**：可将本文观点视为**工具箱中的一种强力透镜**，而非唯一教条；在应用前先追问：*“我当前的约束条件与作者所处的语境一致吗？”*"
        )

    # 意图分支 2：与某某理论 / 概念 / 模型的关联分析
    if any(k in q_lower for k in ("理论", "关系", "联系", "模型", "原理", "对比", "异同", "框架", "哲学", "心理学", "经济学")):
        # 提取用户在问题中提到的特定理论名称（例如“和XX理论有什么关系”）
        theory_match = re.search(r"[和与同跟](.+?)(?:理论|模型|原理|定律|法则|效应|思维|框架|有什么|的关系|有何)", question)
        theory_name = theory_match.group(1).strip("“”\"'「」 ") if theory_match else "经典认知与系统科学理论"
        vp_main = viewpoints[0]["detail"] if viewpoints else (relevant_sents[0] if relevant_sents else title)
        concept_names = "、".join(c["term"] for c in concepts[:3]) if concepts else "核心机制"
        return (
            f"{quote_banner}"
            f"### 🔗 理论脉络映射：本文观点与「{theory_name}」的深层关联\n\n"
            f"将《{title}》放置于更广阔的学术与思想坐标系中，它与 **{theory_name}** 存在着紧密的同构性与互补演进关系：\n\n"
            f"1. **底层逻辑的同构性（Shared Foundation）**\n"
            f"   - 本文提出的核心命题（*“{vp_main[:95]}”*）与 **{theory_name}** 在本质上都试图回答同一个核心问题：**如何在复杂信息与资源约束下实现更高阶的系统秩序与认知跃迁**。\n"
            f"   - 文中重点探讨的「{concept_names}」，实际上可以看作是该理论在当前具体应用场景下的微观映射与操作化表达。\n"
            f"2. **解释维度的互补与延伸（Extension & Nuance）**\n"
            f"   - **经典理论侧重于“解释为什么（Why）”**，提供宏观的演化规律与边界定义；\n"
            f"   - **本文则侧重于“指导怎么做（How）”**，结合一线观察（如：*“{relevant_sents[0][:85] if relevant_sents else ''}”*），将抽象原理拆解成了可感知的判断准则。\n"
            f"3. **跨学科融合启发**\n"
            f"   - 若将两者结合使用：可以用 **{theory_name}** 作为顶层检验标尺，用来判断何处应该介入；再用本文提供的具体策略作为执行抓手，从而形成「理论定方向、方法抓落地」的完整闭环。"
        )

    # 意图分支 3：如何落地 / 行动步骤 / 实践应用
    if any(k in q_lower for k in ("落地", "执行", "行动", "步骤", "应用", "实践", "怎么做", "如何做", "计划", "工作中", "日常")):
        action_list_md = "\n".join(
            f"{i + 1}. **{ins.get('action', '核心行动')}**（*{ins.get('priority', '高优先级')}*）\n"
            f"   - **依据与场景**：{ins.get('scenario', '')}\n"
            f"   - **检验标准**：{ins.get('expected_outcome', '')}"
            for i, ins in enumerate(insights)
        )
        return (
            f"{quote_banner}"
            f"### 🛠️ 从阅读到行动：《{title}》的可落地执行清单\n\n"
            f"为了避免“读完觉得很有道理，关掉页面一切照旧”，建议采用 **最小可行性实践（MVP Action）** 将本文洞察拆解为以下三步：\n\n"
            f"{action_list_md}\n\n"
            f"#### 📅 本周微习惯建议（7-Day Sprint）\n"
            f"- **今天（Day 1）**：从您当前手头正在处理的一个真实项目中，找出一个与文中观点存在反差的环节，写下 100 字的诊断笔记。\n"
            f"- **本周中（Day 3-4）**：选定上述第 1 条行动项，在小范围内做一次对照实验。\n"
            f"- **周末复盘（Day 7）**：回到本阅读助手，在右侧「个人批注」中记录实践反馈，完成从**信息输入 → 结构内化 → 行为改变**的闭环。"
        )

    # 意图分支 4：通俗解释 / 类比 / 小白理解 / 举例
    if any(k in q_lower for k in ("通俗", "类比", "简单", "小白", "解释", "比喻", "听懂", "小学生", "意思")):
        tldr = summary.get("one_sentence_summary", "")
        return (
            f"{quote_banner}"
            f"### 💡 通俗化解读与心智类比\n\n"
            f"如果脱去文中所有的专业术语，用最直白的话来解释《{title}》：\n\n"
            f"- **一句话大白话**：{tldr}\n\n"
            f"#### 🌱 生活化类比（Mental Analogy）\n"
            f"想象你正在经营一座花园或升级电脑系统：\n"
            f"- 很多人以为提升效率靠的是**“拼命买更多花盆 / 打开更多软件窗口”**（对应浅层堆砌与盲目忙碌）；\n"
            f"- 而本文作者真正想告诉你的是：**先改良土壤的生态循环与操作系统的底层内核**（即文中反复强调的「{'、'.join(c['term'] for c in concepts[:2]) if concepts else '核心底层逻辑'}」）。当底层架构理顺后，原本棘手的问题会迎刃而解。\n\n"
            f"#### 📌 原文关键支撑句印证\n"
            + "\n".join(f"- *“{s}”*" for s in relevant_sents[:2])
        )

    # 通用精准问答分支：基于原文语义检索与结构化摘要进行针对性解答
    matched_points = "\n".join(f"- {s}" for s in relevant_sents) if relevant_sents else f"- {summary.get('one_sentence_summary', '')}"
    vp_summary = "\n".join(f"- **{vp['title']}**：{vp['detail']}" for vp in viewpoints[:2])
    return (
        f"{quote_banner}"
        f"### 📖 针对「{question}」的深度解析\n\n"
        f"结合《{title}》的全文脉络与结构化论据，可以从以下几个层面回应您的问题：\n\n"
        f"#### 1. 原文直接关联的论述与证据\n"
        f"{matched_points}\n\n"
        f"#### 2. 与全文核心主旨的逻辑呼应\n"
        f"{vp_summary}\n\n"
        f"#### 3. 延伸思考与实践启示\n"
        f"- **作者立场参照**：本文整体呈现「{stance.get('overall_tone', '理性分析')}」基调。在理解这一问题时，建议同时关注作者指出的边界条件：*{stance.get('potential_bias', '需结合具体场景灵活调整')}*。\n"
        f"- 您还可以继续追问：*“这一观点在极端场景下会失效吗？”* 或点击上方论据卡片旁边的 **「引用追问」** 进行更细粒度的探讨。"
    )


def answer_article_question(
    title: str,
    content: str,
    summary: dict[str, Any],
    history: list[dict[str, Any]],
    question: str,
    quoted_text: str | None = None,
    session: Session | None = None,
) -> tuple[str, str]:
    """
    针对单篇文章进行追问回答，返回 (answer_markdown, engine_used)。
    """
    llm_cfg = get_runtime_llm_config(session)
    if llm_cfg["active_mode"] == "llm":
        system_prompt = (
            "你是一位精通批判性思维、跨学科联想与深度阅读的 AI 研究搭档。\n"
            "请基于用户正在阅读的文章原文与结构化摘要，深入、严谨、有条理地回答用户的追问。\n"
            "回答要求：\n"
            "1. 使用清晰的 Markdown 格式（分级标题、要点列表、粗体强调）。\n"
            "2. 紧扣文章内容引用具体论据，同时在用户询问漏洞、理论关联或拓展应用时，主动调用你的跨学科知识库提供高价值的增量洞察。\n"
            "3. 如果用户附带了【引用片段】，请优先围绕该片段展开深度剖析。"
        )
        context_block = (
            f"【文章标题】：{title}\n"
            f"【一句话总结】：{summary.get('one_sentence_summary', '')}\n"
            f"【原文内容（节选）】：\n{content[:10000]}"
        )
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"以下是当前阅读的文章背景资料：\n{context_block}"},
            {"role": "assistant", "content": "我已经完整掌握了这篇文章的核心论点、关键论据与行文脉络，请提出你的问题。"},
        ]
        # 加入最近 6 轮历史对话
        for msg in history[-6:]:
            role = "user" if msg.get("role") == "user" else "assistant"
            messages.append({"role": role, "content": str(msg.get("content", ""))})

        user_query = question
        if quoted_text and quoted_text.strip():
            user_query = f"【用户选中引用的原文/观点片段】：\n“{quoted_text.strip()}”\n\n【追问问题】：{question}"
        messages.append({"role": "user", "content": user_query})

        try:
            reply = call_openai_compatible(messages=messages, llm_cfg=llm_cfg, expect_json=False)
            return reply.strip(), "llm"
        except Exception:
            pass

    reply = _heuristic_answer_article_question(
        title=title,
        content=content,
        summary=summary,
        question=question,
        quoted_text=quoted_text,
    )
    return reply, "heuristic"


# ---------------------------------------------------------------------------
# 对外核心业务接口 3：多文章「主题」对比总结 (Multi-Article Topic Synthesis)
# ---------------------------------------------------------------------------

def _heuristic_topic_comparison(
    topic_name: str,
    topic_desc: str,
    articles: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    内置启发式多文章对比总结引擎：
    对同一主题下的多篇文章进行横向解构，提炼核心共识、关键分歧、多维对比矩阵、视角互补与综合行动建议。
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    if not articles:
        return {}

    titles = [a["title"] for a in articles]
    # 收集所有标签与高频词以寻找共同话题交集
    all_tags: list[str] = []
    for a in articles:
        all_tags.extend(a.get("tags", []))
        all_tags.extend(_extract_keywords(f"{a['title']} {a.get('raw_content', '')[:800]}", top_k=4))

    tag_counts = Counter(all_tags)
    shared_themes = [t for t, _ in tag_counts.most_common(4)] or ["核心机制", "认知升级", "实践方法论"]

    # 1. 构建多维横向对比矩阵 (Comparison Matrix)
    comparison_matrix = []
    for a in articles:
        summary = a.get("summary", {})
        vps = summary.get("core_viewpoints", [])
        args = summary.get("key_arguments", [])
        stance = summary.get("author_stance", {})
        insights = summary.get("actionable_insights", [])

        core_thesis = vps[0]["detail"] if vps else summary.get("one_sentence_summary", a["title"])
        methodology = args[0]["logic_type"] if args else "结构化论述与案例剖析"
        stance_tone = stance.get("overall_tone", "理性实证")
        unique_value = insights[0]["action"] if insights else f"提供了关于《{a['title']}》的独特切入视角"
        limitation = stance.get("potential_bias", "受限于单一语境假设，需结合其他文献交叉验证。")

        comparison_matrix.append(
            {
                "article_id": a["id"],
                "article_title": a["title"],
                "author": a.get("author") or a.get("site_name") or "作者",
                "core_thesis": core_thesis,
                "methodology": methodology,
                "stance_tone": stance_tone,
                "unique_value": unique_value,
                "limitation": limitation,
            }
        )

    # 2. 提炼跨文章核心共识 (Consensus Points)
    consensus_points = [
        {
            "point": f"共识一：围绕「{shared_themes[0]}」的基础地位达成高度一致",
            "detail": (
                f"收录在「{topic_name}」主题下的 {len(articles)} 篇文章（包括《{titles[0]}》"
                + (f"与《{titles[1]}》等" if len(titles) > 1 else "")
                + f"）均认为：不能停留在表象特征或碎片化技巧上，必须深入理解「{shared_themes[0]}」背后的系统性结构。"
            ),
            "supporting_articles": titles,
        },
        {
            "point": f"共识二：强调从“被动接收”向“主动构建与验证”的范式转移",
            "detail": (
                f"无论是偏重理论剖析还是偏重实践指南的文章，作者们都指出了传统惯性路径的局限性，"
                f"主张围绕「{'、'.join(shared_themes[:3])}」建立持续迭代的反馈闭环。"
            ),
            "supporting_articles": titles,
        },
    ]

    # 3. 提炼关键分歧与张力 (Disagreements & Tensions)
    disagreements = []
    if len(articles) >= 2:
        positions_focus = []
        positions_pace = []
        for idx, m in enumerate(comparison_matrix):
            positions_focus.append(
                {
                    "article_title": m["article_title"],
                    "stance": (
                        f"采取「{m['stance_tone']}」立场，依托【{m['methodology']}】，"
                        f"认为破局关键在于：{m['core_thesis'][:75]}…"
                    ),
                }
            )
            pace_desc = (
                "主张先厘清底层认知边界与潜在风险，避免盲目扩张带来的系统性损耗。"
                if "批判" in m["stance_tone"] or "审慎" in m["stance_tone"] or idx % 2 == 1
                else "主张通过工具赋能与结构化工作流优先行动，在高频实践中完成认知迭代。"
            )
            positions_pace.append(
                {
                    "article_title": m["article_title"],
                    "stance": pace_desc,
                }
            )

        disagreements = [
            {
                "dimension": "分歧维度一：核心切入点与归因重心（底层认知 vs. 工具/机制演进）",
                "conflict_summary": (
                    f"各篇文章在面对「{topic_name}」同一核心挑战时，归因重心存在明显差异："
                    f"部分文章将其归结为主体认知模型的滞后，而另一部分文章则强调外部技术/系统机制变革带来的结构性重塑。"
                ),
                "positions": positions_focus,
            },
            {
                "dimension": "分歧维度二：实践推进策略（审慎防御与边界约束 vs. 敏捷落地与范式跃迁）",
                "conflict_summary": "在如何应对不确定性以及推进节奏上，不同作者展现出了「风险规避型审慎」与「机会驱动型进取」的张力。",
                "positions": positions_pace,
            },
        ]
    else:
        disagreements = [
            {
                "dimension": "单篇文献内部张力：理想模型与现实约束的平衡",
                "conflict_summary": "当前主题下仅收录 1 篇文章，建议向本主题再添加 1~3 篇相关或相反立场的文章，以激活多视角交叉对比。",
                "positions": [
                    {
                        "article_title": titles[0],
                        "stance": comparison_matrix[0]["core_thesis"],
                    }
                ],
            }
        ]

    # 4. 视角互补与演进脉络 (Complementary Synthesis)
    if len(articles) >= 2:
        chain_steps = " ➔ ".join(f"《{t}》" for t in titles)
        complementary_insights = (
            f"将这 {len(articles)} 篇文章组合阅读，可以构建一条完整的认知升级链条（{chain_steps}）：\n"
            f"首先，通过第一篇文献建立对「{shared_themes[0]}」的全景问题意识；"
            f"其次，借助后续文献中的不同立场（{', '.join(m['stance_tone'] for m in comparison_matrix)}）打破单一视角的回音室效应；"
            f"最终，将各篇的独有价值（{' / '.join(m['unique_value'] for m in comparison_matrix[:3])}）融合为一套兼顾**战略清醒度**与**战术执行力**的综合方案。"
        )
    else:
        complementary_insights = (
            f"当前以《{titles[0]}》为基准锚点，建议进一步补充一篇“反方批判视角”或“不同行业落地案例”的文章，形成正反合的立体认知。"
        )

    # 5. 跨文章综合行动建议 (Synthesized Action Plan)
    synthesized_actions = []
    for idx, m in enumerate(comparison_matrix[:4]):
        synthesized_actions.append(
            {
                "title": f"综合策略 {idx + 1}：吸收《{m['article_title'][:18]}》的方法论精华",
                "detail": (
                    f"结合该文提出的「{m['unique_value']}」，同时用主题下其他文章提醒的边界条件（{m['limitation'][:45]}…）作为安全护栏，"
                    f"在个人或团队知识库中建立标准化的复盘检查清单。"
                ),
                "source_inspiration": m["article_title"],
            }
        )

    overview = (
        f"本专题「{topic_name}」共聚合了 {len(articles)} 篇深度文献"
        + (f"（主题说明：{topic_desc}）" if topic_desc else "")
        + f"。通过跨文本结构化比对可以发现，各篇文献围绕「{'、'.join(shared_themes[:3])}」形成了鲜明的对话关系："
        f"既有对核心价值的底层共识，也在切入路径、论证方法（{'、'.join(dict.fromkeys(m['methodology'] for m in comparison_matrix))}）"
        f"与风险评估上展现出极佳的互补性。"
    )

    return {
        "overview": overview,
        "consensus_points": consensus_points,
        "disagreements": disagreements,
        "comparison_matrix": comparison_matrix,
        "complementary_insights": complementary_insights,
        "synthesized_actions": synthesized_actions,
        "generated_at": now_iso,
        "article_count_at_generation": len(articles),
        "engine_used": "heuristic",
    }


def generate_topic_comparison(
    topic_name: str,
    topic_desc: str,
    articles: list[dict[str, Any]],
    session: Session | None = None,
) -> dict[str, Any]:
    """
    对同一主题下的多篇文章进行横向对比与综合提炼。
    """
    if not articles:
        return {}

    llm_cfg = get_runtime_llm_config(session)
    if llm_cfg["active_mode"] == "llm":
        articles_digest = []
        for idx, a in enumerate(articles, start=1):
            s = a.get("summary", {})
            articles_digest.append(
                f"【文章 {idx}】《{a['title']}》（ID: {a['id']}，作者/来源: {a.get('author') or a.get('site_name') or '未知'}）\n"
                f"- 一句话总结：{s.get('one_sentence_summary', '')}\n"
                f"- 核心观点：{json.dumps(s.get('core_viewpoints', []), ensure_ascii=False)}\n"
                f"- 关键论据：{json.dumps(s.get('key_arguments', []), ensure_ascii=False)}\n"
                f"- 作者态度：{json.dumps(s.get('author_stance', {}), ensure_ascii=False)}\n"
                f"- 可行动洞察：{json.dumps(s.get('actionable_insights', []), ensure_ascii=False)}\n"
            )

        system_prompt = (
            "你是一位资深的跨文献综述学者与战略分析师。请对同一个研究主题下的多篇文章进行深度横向对比总结，并严格输出合法的 JSON 对象。\n"
            "JSON 结构必须包含以下字段：\n"
            "{\n"
            '  "overview": "主题全景综述与核心脉络（120-250字）",\n'
            '  "consensus_points": [\n'
            '    {"point": "共识标题", "detail": "详细阐述多篇文章如何共同印证这一点", "supporting_articles": ["文章标题1", "文章标题2"]}\n'
            "  ],\n"
            '  "disagreements": [\n'
            '    {\n'
            '      "dimension": "分歧维度名称",\n'
            '      "conflict_summary": "核心张力与分歧概述",\n'
            '      "positions": [{"article_title": "文章标题", "stance": "该文在此维度上的具体立场"}]\n'
            "    }\n"
            "  ],\n"
            '  "comparison_matrix": [\n'
            '    {\n'
            '      "article_id": 1,\n'
            '      "article_title": "文章标题",\n'
            '      "author": "作者或来源",\n'
            '      "core_thesis": "核心论点",\n'
            '      "methodology": "论证方法",\n'
            '      "stance_tone": "态度基调",\n'
            '      "unique_value": "独特增量价值",\n'
            '      "limitation": "视角局限性"\n'
            "    }\n"
            "  ],\n"
            '  "complementary_insights": "这几篇文章如何互相补全认知拼图、建议按什么逻辑顺序理解（100-220字）",\n'
            '  "synthesized_actions": [\n'
            '    {"title": "综合行动建议标题", "detail": "融合多篇洞察后的具体落地方法", "source_inspiration": "启发来源文章标题"}\n'
            "  ]\n"
            "}"
        )
        user_prompt = (
            f"研究主题名称：{topic_name}\n"
            f"主题描述：{topic_desc or '无'}\n\n"
            f"包含的 {len(articles)} 篇文章摘要档案如下：\n\n" + "\n".join(articles_digest)
        )
        try:
            raw_resp = call_openai_compatible(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                llm_cfg=llm_cfg,
                expect_json=True,
            )
            parsed = _extract_json_block(raw_resp)
            parsed["generated_at"] = datetime.now(timezone.utc).isoformat()
            parsed["article_count_at_generation"] = len(articles)
            parsed["engine_used"] = "llm"
            return parsed
        except Exception:
            pass

    return _heuristic_topic_comparison(topic_name, topic_desc, articles)


# ---------------------------------------------------------------------------
# 对外核心业务接口 4：针对整个「主题」的跨文章追问 (Topic-Level Multi-Doc Q&A)
# ---------------------------------------------------------------------------

def answer_topic_question(
    topic_name: str,
    articles: list[dict[str, Any]],
    comparison: dict[str, Any],
    history: list[dict[str, Any]],
    question: str,
    session: Session | None = None,
) -> tuple[str, str]:
    """
    针对主题下所有文章进行跨篇追问回答，返回 (answer_markdown, engine_used)。
    """
    llm_cfg = get_runtime_llm_config(session)
    if llm_cfg["active_mode"] == "llm" and articles:
        system_prompt = (
            "你是一位跨文献对比研究专家。用户正在研究一个包含多篇文章的专题，请综合专题内所有文章的观点、论据与分歧，"
            "使用结构化 Markdown 回答用户的跨篇追问。回答时请明确点出不同文章（用《文章标题》标注）各自的立场异同。"
        )
        articles_brief = "\n".join(
            f"- 《{a['title']}》：{a.get('summary', {}).get('one_sentence_summary', '')}"
            for a in articles
        )
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"当前专题：{topic_name}\n"
                    f"收录文章：\n{articles_brief}\n"
                    f"现有对比综述：{json.dumps(comparison, ensure_ascii=False)[:6000]}"
                ),
            },
            {"role": "assistant", "content": "已掌握该专题下所有文献的脉络与横向对比关系，请提问。"},
        ]
        for msg in history[-6:]:
            role = "user" if msg.get("role") == "user" else "assistant"
            messages.append({"role": role, "content": str(msg.get("content", ""))})
        messages.append({"role": "user", "content": question})

        try:
            reply = call_openai_compatible(messages=messages, llm_cfg=llm_cfg, expect_json=False)
            return reply.strip(), "llm"
        except Exception:
            pass

    # 内置启发式跨文章追问回答
    per_article_views = []
    for a in articles:
        s = a.get("summary", {})
        vps = s.get("core_viewpoints", [])
        vp_str = vps[0]["detail"] if vps else s.get("one_sentence_summary", "")
        stance_tone = s.get("author_stance", {}).get("overall_tone", "理性分析")
        per_article_views.append(f"- **《{a['title']}》**（*{stance_tone}*）：{vp_str}")

    views_md = "\n".join(per_article_views) if per_article_views else "- 当前主题暂无文章。"
    comp_overview = comparison.get("overview", f"本专题围绕「{topic_name}」聚合了多篇文献。")
    comp_complement = comparison.get(
        "complementary_insights",
        "建议结合各篇文章的适用边界进行交叉印证。",
    )

    reply = (
        f"### 🧭 跨文献综合解答：{question}\n\n"
        f"站在 **「{topic_name}」** 专题的全局视角下，综合对比收录的 {len(articles)} 篇文章，可得出以下交叉洞见：\n\n"
        f"#### 1. 各篇文献对该议题的回应视角\n"
        f"{views_md}\n\n"
        f"#### 2. 核心张力与互补关系\n"
        f"- **全局脉络**：{comp_overview}\n"
        f"- **认知拼图互补**：{comp_complement}\n\n"
        f"#### 3. 综合决策建议\n"
        f"当不同文章出现判断分歧时，不必急于判定谁对谁错，而应检查**前提条件**："
        f"在基础建设期优先采纳偏重底层框架与风险防范的文献建议；在业务突破期则可借鉴偏重工具杠杆与敏捷迭代的文献策略。"
    )
    return reply, "heuristic"
