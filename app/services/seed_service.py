"""
初始化演示数据服务 (Demo Seed Data Service)

在首次启动或用户点击「加载示例数据」时，提供 3 篇立场鲜明、论据充实的深度文章，
并自动归入一个「AI 时代的认知升级与深度阅读」对比主题，让用户开箱即可完整体验所有核心功能。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Article, ArticleMessage, Topic
from app.services.article_service import ask_followup_question, create_article
from app.services.topic_service import create_topic


SAMPLE_ARTICLES = [
    {
        "title": "警惕“认知外包”陷阱：为什么 AI 摘要不能替代深度阅读",
        "author": "林思远 · 认知科学专栏",
        "source_type": "text",
        "url": "https://example.com/cognitive-outsourcing-trap",
        "raw_text": """
在生成式 AI 成为日常基础设施的今天，越来越多的人习惯将几万字的长文、学术论文甚至整本书直接丢给大模型，用 10 秒钟浏览完那几行整齐的要点列表，便误以为自己已经“读完”并“掌握”了这些知识。这种被称为“认知外包（Cognitive Outsourcing）”的现象，正在悄然引发一场隐蔽的思维退化危机。

核心在于，知识的本质从来不是静态的结论字符，而是作者在推导结论时经历的推理摩擦、证据权衡与边界挣扎。实验心理学研究显示，当两组受试者分别阅读完整论述文章与仅阅读 AI 提炼的结论摘要时，在 48 小时后的迁移应用测试中，仅看摘要组的表现比深度阅读组低 43%，且更容易陷入“元认知错觉（Illusion of Explanatory Depth）”——即高估自己对复杂机制的理解程度。

原因很简单：大脑的神经可塑性遵循“用进废退”原则。当我们跳过了对原始论据的审视、跳过了寻找逻辑漏洞的认知阻力（Desirable Difficulty），我们的前额叶皮层就失去了构建高维心智模型的训练机会。你记住的只是别人的口号，而不是推理的肌肉。

但这是否意味着我们应当拒绝 AI 阅读工具？恰恰相反。真正的破局之道在于改变人机分工的范式：不应该让 AI 替你“读完并下结论”，而应该把 AI 当作苏格拉底式的“陪练搭档”和“结构化脚手架”。

首先，应当利用 AI 快速建立文章的鸟瞰地图（核心论点、论证类型与作者立场），用于筛选哪些内容值得投入宝贵的注意力精读；其次，在阅读过程中，主动对文中观点发起批判性追问——例如追问“这个论点依赖什么隐含假设？”“如果换一个行业周期，这个案例还成立吗？”；最后，必须坚持用自己的话写下哪怕只有 100 字的批注与行动计划。只有经过主动提问与重构的信息，才会真正内化为属于你自己的认知资产。
""".strip(),
    },
    {
        "title": "构建你的“外脑工作流”：如何用结构化信息处理将研究效率提升 5 倍",
        "author": "陈航 · 知识工程实践者",
        "source_type": "text",
        "url": "https://example.com/structured-second-brain-workflow",
        "raw_text": """
现代知识工作者面临的最大瓶颈，早就不是“信息匮乏”，而是灾难性的“信噪比过低”。每天涌入的信息流中，超过 80% 的商业报道与行业文章充斥着冗长的背景铺垫、情绪化渲染和重复案例，真正具有增量价值的洞察往往不到全文的 15%。如果对所有材料都采取传统的逐字线性阅读，无异于在信息洪流中用勺子淘金。

高效研究者的核心竞争力，在于构建一套标准化的“结构化信息摄入流水线”。通过对硅谷与国内 120 位顶尖分析师、产品负责人及独立研究者的调研发现，高产出人群普遍采用“三层漏斗阅读法”：第一层是结构化拆解，强制将任何非结构化长文解构为【核心观点、关键论据、作者立场、可行动洞察】四个标准槽位；第二层是跨源交叉比对，不轻信单一信源，而是把同一主题下的 3 到 5 篇不同立场文章放进同一个专题矩阵中横向碰撞；第三层则是面向产出的最小行动闭环。

数据证明，当我们将单篇线性阅读转变为“AI 结构化预解析 + 主题矩阵横向对比”的工作流后，完成一份新领域深度调研报告的平均耗时从 18 小时缩短至 3.5 小时，效率提升超过 5 倍，而且由于引入了多篇文章的共识与分歧比对，决策盲区反而大幅减少。

因此，我们需要建立全新的阅读工作流标准：第一，永远不要孤立地读一篇文章，养成“主题式阅读（Topic-based Reading）”的习惯，每遇到重要议题，立即建立主题并收集正反多方文献；第二，使用统一的结构化卡片提取每篇文章的论据与偏见，让不同作者在你的知识库里“同台辩论”；第三，规定每次阅读必须提炼出至少一条本周可验证的行动项（Actionable Insight），无法转化为行动或模型修正的阅读，本质上只是智识上的娱乐消遣。
""".strip(),
    },
    {
        "title": "从“卡片盒笔记”到“动态思辨网络”：人机协同阅读的第三条道路",
        "author": "卢曼实验室 · 系统思维研究组",
        "source_type": "text",
        "url": "https://example.com/dynamic-dialectical-network",
        "raw_text": """
围绕“AI 时代应该坚持慢速精读还是追求高效速读”的争论，本质上陷入了非黑即白的二元对立误区。社会学家尼克拉斯·卢曼（Niklas Luhmann）生前依靠卡片盒笔记法（Zettelkasten）出版了 70 多部专著与 400 多篇论文，他早已揭示了知识生产的本质规律：真正产生洞见的，既不是孤立的精读，也不是机械的摘抄，而是卡片与卡片之间的“结构化连接与对话”。

在传统手写卡片时代，建立跨文献连接与寻找反例的成本极高，往往需要数月甚至数年的积累才能浮现出一个主题簇。而大语言模型的出现，第一次让“实时跨文本思辨网络”成为可能。当我们把审慎的批判性精读（关注逻辑漏洞与隐含假设）与高效的工程化结构拆解（四维摘要与多文档对比矩阵）融合在一起时，人机协同阅读的第三条道路便清晰浮现。

在这条演进路径上，人类大脑与 AI 各自承担不可替代的职责：AI 负责消除机械性的信息整理摩擦——提取核心观点、标注论证类型、对齐不同文章在相同维度上的分歧；而人类读者则掌握“问题定义权”与“价值判断权”——决定追问什么尖锐问题、决定采纳哪一方的实践建议、并结合自身真实业务语境撰写个人批注。

建议每一位终身学习者立即升级自己的阅读协议：首先，在导入文章后先看【作者态度与潜在偏见】，带着批判性滤镜进入文本；其次，善用“引用追问”功能，把文中看似理所当然的金句拿出来与经典理论框架（如第一性原理、系统动力学、反脆弱理论）做交叉质询；最后，定期在「主题对比」视图中审视不同文章的共识与分歧，将碎片化的单篇阅读沉淀为可复用的领域知识图谱。
""".strip(),
    },
]


def seed_initial_data_if_empty(session: Session, force: bool = False) -> dict[str, int]:
    """
    检查数据库是否为空；若为空（或 force=True），则自动注入 3 篇示例文章、追问示例与 1 个多文章对比主题。
    """
    existing_count = session.query(Article).count()
    if existing_count > 0 and not force:
        return {"articles_created": 0, "topics_created": 0}

    created_articles: list[Article] = []
    for item in SAMPLE_ARTICLES:
        art = create_article(
            session=session,
            source_type=item["source_type"],
            url=item["url"],
            raw_text=item["raw_text"],
            title=item["title"],
            author=item["author"],
        )
        created_articles.append(art)

    if created_articles:
        # 将第一篇设为星标收藏，并写入示例个人批注与追问记录
        first_art = created_articles[0]
        first_art.is_favorite = True
        first_art.user_notes = (
            "💡 核心启发：\n"
            "1. “元认知错觉”非常值得警惕——看懂了 AI 摘要不等于自己拥有了推导能力。\n"
            "2. 下一步行动：以后读深度长文时，先看结构化摘要定位重点，再至少发起 2 次批判性追问。"
        )
        ask_followup_question(
            session=session,
            article_id=first_art.id,
            question="这篇文章的核心观点有什么潜在漏洞？如果面对海量文献必须快速筛选时该怎么办？",
            quoted_text="当两组受试者分别阅读完整论述文章与仅阅读 AI 提炼的结论摘要时，在 48 小时后的迁移应用测试中，仅看摘要组的表现比深度阅读组低 43%",
        )

    # 创建跨文章对比「主题」并自动生成多篇对比总结报告
    topic = create_topic(
        session=session,
        name="AI 时代的深度阅读与认知升级",
        description="对比探讨生成式 AI 介入阅读流程后，“警惕认知退化”、“构建高效外脑工作流”与“卢曼动态思辨网络”三种代表性立场的共识与张力。",
        color="#4f46e5",
        article_ids=[a.id for a in created_articles],
        auto_compare=True,
    )

    session.commit()
    return {
        "articles_created": len(created_articles),
        "topics_created": 1 if topic else 0,
    }
