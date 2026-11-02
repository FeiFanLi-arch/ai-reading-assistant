/**
 * 个人 AI 阅读助手 (Personal AI Reading Assistant) - 前端核心交互应用
 *
 * 功能模块：
 * 1. 全局状态管理 (State) 与统一 REST API 请求封装
 * 2. 左侧知识库历史文章列表、全文搜索、标签与状态筛选
 * 3. 单篇文章结构化摘要渲染（核心观点、关键论据、作者态度、可行动洞察、核心概念）
 * 4. 原文阅读器划词引用追问 & 观点卡片一键引用追问 (Quote-to-Ask)
 * 5. 多文章「主题」聚合管理、横向对比矩阵渲染与跨文章追问
 * 6. Markdown 导出、个人阅读批注保存与 AI 引擎运行时热配置
 */

(function () {
    "use strict";

    // ======================= 1. 全局应用状态 =======================
    const state = {
        mode: "articles", // 'articles' | 'topics'
        articles: [],
        topics: [],
        samples: [],
        stats: {},
        currentArticle: null,
        currentTopic: null,
        activeTab: "summary", // 'summary' | 'original' | 'notes'
        filters: {
            search: "",
            status: "all", // 'all' | 'favorite' | 'reading' | 'completed'
            tag: "",
        },
        quotedText: null,
    };

    // 默认批判性追问快捷模板
    const DEFAULT_ARTICLE_PROMPTS = [
        "🔍 这个观点有什么潜在逻辑漏洞或隐含假设？",
        "🔗 文中观点和第一性原理或经典理论有什么关系？",
        "⚖️ 如果站在反对者立场，最有力的反驳论据是什么？",
        "🛠️ 如何将文中的可行动洞察转化为本周可执行的 3 个步骤？",
        "💡 请用通俗易懂的生活类比解释本文核心逻辑。",
    ];

    const DEFAULT_TOPIC_PROMPTS = [
        "⚡ 这几篇文章在核心问题上的根本分歧是什么？",
        "🤝 如何把这几篇文章的方法论整合成一套完整方案？",
        "🧭 对比来看，哪篇文章的论据最扎实？各自有什么盲区？",
    ];

    const LLM_PROVIDER_PRESETS = {
        openai: { base_url: "https://api.openai.com/v1", model: "gpt-4o-mini" },
        deepseek: { base_url: "https://api.deepseek.com/v1", model: "deepseek-chat" },
        qwen: { base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen-plus" },
        siliconflow: { base_url: "https://api.siliconflow.cn/v1", model: "Qwen/Qwen2.5-72B-Instruct" },
        ollama: { base_url: "http://localhost:11434/v1", model: "qwen2.5:7b" },
    };

    // ======================= 2. 工具函数与轻量 Markdown 渲染 =======================
    function escapeHtml(str) {
        if (str === null || str === undefined) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function renderMarkdown(mdText) {
        if (!mdText) return "";
        const lines = String(mdText).split(/\r?\n/);
        const htmlLines = [];
        let inList = false;

        for (let rawLine of lines) {
            const line = rawLine.trim();
            if (!line) {
                if (inList) {
                    htmlLines.push("</ul>");
                    inList = false;
                }
                continue;
            }

            if (line.startsWith("#### ")) {
                if (inList) { htmlLines.push("</ul>"); inList = false; }
                htmlLines.push(`<h4>${formatInlineMd(line.slice(5))}</h4>`);
            } else if (line.startsWith("### ")) {
                if (inList) { htmlLines.push("</ul>"); inList = false; }
                htmlLines.push(`<h3>${formatInlineMd(line.slice(4))}</h3>`);
            } else if (line.startsWith("> ")) {
                if (inList) { htmlLines.push("</ul>"); inList = false; }
                htmlLines.push(`<blockquote>${formatInlineMd(line.slice(2))}</blockquote>`);
            } else if (/^[-*]\s+/.test(line) || /^\d+\.\s+/.test(line)) {
                if (!inList) {
                    htmlLines.push("<ul>");
                    inList = true;
                }
                const itemText = line.replace(/^([-*]|\d+\.)\s+/, "");
                htmlLines.push(`<li>${formatInlineMd(itemText)}</li>`);
            } else {
                if (inList) { htmlLines.push("</ul>"); inList = false; }
                htmlLines.push(`<p>${formatInlineMd(line)}</p>`);
            }
        }
        if (inList) htmlLines.push("</ul>");
        return htmlLines.join("");
    }

    function formatInlineMd(text) {
        let safe = escapeHtml(text);
        safe = safe.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
        safe = safe.replace(/\*(.+?)\*/g, "<em>$1</em>");
        safe = safe.replace(/`(.+?)`/g, "<code>$1</code>");
        return safe;
    }

    function formatDateShort(isoStr) {
        if (!isoStr) return "";
        try {
            const d = new Date(isoStr);
            const month = String(d.getMonth() + 1).padStart(2, "0");
            const day = String(d.getDate()).padStart(2, "0");
            const hours = String(d.getHours()).padStart(2, "0");
            const mins = String(d.getMinutes()).padStart(2, "0");
            return `${month}-${day} ${hours}:${mins}`;
        } catch (_) {
            return "";
        }
    }

    function showToast(message, type = "info") {
        const container = document.getElementById("toast-container");
        if (!container) return;
        const item = document.createElement("div");
        item.className = `toast-item ${type}`;
        item.textContent = message;
        container.appendChild(item);
        setTimeout(() => {
            item.remove();
        }, 3200);
    }

    async function apiFetch(url, options = {}) {
        const defaultHeaders = { "Content-Type": "application/json" };
        const config = {
            ...options,
            headers: { ...defaultHeaders, ...(options.headers || {}) },
        };
        const response = await fetch(url, config);
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.error || `请求失败 (HTTP ${response.status})`);
        }
        return data;
    }

    // ======================= 3. 全局统计与侧边栏加载 =======================
    async function refreshStatsAndSidebar() {
        const [statsData, topicsData] = await Promise.all([
            apiFetch("/api/system/stats"),
            apiFetch("/api/topics"),
        ]);
        state.stats = statsData;
        state.topics = topicsData.items || [];

        // 顶部统计栏
        document.getElementById("stat-articles").textContent = statsData.total_articles || 0;
        document.getElementById("stat-topics").textContent = statsData.total_topics || 0;
        document.getElementById("stat-questions").textContent = statsData.total_questions || 0;
        document.getElementById("stat-words").textContent = (statsData.total_words || 0).toLocaleString();

        // 引擎状态指示器
        const dot = document.getElementById("engine-status-dot");
        const txt = document.getElementById("engine-status-text");
        if (statsData.active_engine === "llm") {
            dot.classList.add("llm");
            txt.textContent = `大模型: ${statsData.llm_model}`;
        } else {
            dot.classList.remove("llm");
            txt.textContent = "内置智能引擎 (可配 Key)";
        }

        document.getElementById("sidebar-topic-count").textContent = state.topics.length;
        renderSidebarTags(statsData.tags || []);
        renderTopicHistoryList();
        await loadArticlesList();
    }

    function renderSidebarTags(tags) {
        const bar = document.getElementById("sidebar-tags-bar");
        if (!tags || tags.length === 0) {
            bar.classList.add("hidden");
            return;
        }
        bar.classList.remove("hidden");
        bar.innerHTML = tags
            .map((t) => {
                const isActive = state.filters.tag === t.name;
                return `<button class="tag-filter-pill ${isActive ? "active" : ""}" data-tag="${escapeHtml(t.name)}">#${escapeHtml(t.name)} (${t.count})</button>`;
            })
            .join("");

        bar.querySelectorAll(".tag-filter-pill").forEach((btn) => {
            btn.addEventListener("click", () => {
                const clickedTag = btn.getAttribute("data-tag");
                state.filters.tag = state.filters.tag === clickedTag ? "" : clickedTag;
                renderSidebarTags(tags);
                loadArticlesList();
            });
        });
    }

    async function loadArticlesList() {
        const params = new URLSearchParams();
        if (state.filters.search) params.set("search", state.filters.search);
        if (state.filters.tag) params.set("tag", state.filters.tag);
        if (state.filters.status === "favorite") {
            params.set("favorite", "1");
        } else if (state.filters.status !== "all") {
            params.set("status", state.filters.status);
        }

        const data = await apiFetch(`/api/articles?${params.toString()}`);
        state.articles = data.items || [];
        document.getElementById("sidebar-article-count").textContent = state.articles.length;
        renderArticleHistoryList();
    }

    function renderArticleHistoryList() {
        const container = document.getElementById("article-history-list");
        if (state.articles.length === 0) {
            container.innerHTML = `<div class="qa-empty-placeholder">暂无匹配的文章记录</div>`;
            return;
        }

        container.innerHTML = state.articles
            .map((art) => {
                const isActive = state.mode === "articles" && state.currentArticle && state.currentArticle.id === art.id;
                const starIcon = art.is_favorite ? "⭐ " : "";
                const topicBadges = (art.topics || [])
                    .map((tp) => `<span class="mini-badge topic-pill">🗂️ ${escapeHtml(tp.name)}</span>`)
                    .join("");
                const tagBadges = (art.tags || [])
                    .slice(0, 2)
                    .map((tg) => `<span class="mini-badge">#${escapeHtml(tg)}</span>`)
                    .join("");

                return `
                <div class="history-card ${isActive ? "active" : ""}" data-article-id="${art.id}">
                    <div class="history-card-top">
                        <span>${escapeHtml((art.source_type || "text").toUpperCase())} · ${art.word_count} 字</span>
                        <span>${formatDateShort(art.created_at)}</span>
                    </div>
                    <div class="history-card-title">${starIcon}${escapeHtml(art.title)}</div>
                    <div class="history-card-summary">${escapeHtml(art.one_sentence_summary || art.content_preview || "")}</div>
                    <div class="history-card-badges">
                        ${topicBadges}
                        ${tagBadges}
                    </div>
                </div>
            `;
            })
            .join("");

        container.querySelectorAll(".history-card").forEach((card) => {
            card.addEventListener("click", () => {
                const id = Number(card.getAttribute("data-article-id"));
                selectArticle(id);
            });
        });
    }

    function renderTopicHistoryList() {
        const container = document.getElementById("topic-history-list");
        if (state.topics.length === 0) {
            container.innerHTML = `<div class="qa-empty-placeholder">尚未创建研究主题，点击上方按钮新建</div>`;
            return;
        }

        container.innerHTML = state.topics
            .map((tp) => {
                const isActive = state.mode === "topics" && state.currentTopic && state.currentTopic.id === tp.id;
                return `
                <div class="history-card ${isActive ? "active" : ""}" data-topic-id="${tp.id}">
                    <div class="history-card-top">
                        <span style="display:inline-flex;align-items:center;gap:5px;">
                            <span class="topic-badge-dot" style="background:${escapeHtml(tp.color || "#4f46e5")}"></span>
                            收录 ${tp.article_count} 篇文章
                        </span>
                        <span>${tp.has_comparison ? "✅ 已生成对比" : "⏳ 待对比"}</span>
                    </div>
                    <div class="history-card-title">${escapeHtml(tp.name)}</div>
                    <div class="history-card-summary">${escapeHtml(tp.description || "点击查看多篇横向对比综述与共识分歧矩阵")}</div>
                </div>
            `;
            })
            .join("");

        container.querySelectorAll(".history-card").forEach((card) => {
            card.addEventListener("click", () => {
                const id = Number(card.getAttribute("data-topic-id"));
                selectTopic(id);
            });
        });
    }

    // ======================= 4. 单篇文章详情渲染 =======================
    async function selectArticle(articleId) {
        state.mode = "articles";
        updateSidebarModeUI();
        clearQuotedText();

        const detail = await apiFetch(`/api/articles/${articleId}`);
        state.currentArticle = detail;
        renderArticleDetailView(detail);
        renderArticleHistoryList();
    }

    function renderArticleDetailView(article) {
        document.getElementById("workspace-empty-state").classList.add("hidden");
        document.getElementById("topic-workspace-view").classList.add("hidden");
        document.getElementById("article-workspace-view").classList.remove("hidden");

        document.getElementById("article-source-badge").textContent = (article.source_type || "text").toUpperCase();
        document.getElementById("article-author-meta").textContent = article.author
            ? `✍️ ${article.author}`
            : article.site_name
            ? `🌐 ${article.site_name}`
            : "✍️ 未知来源";
        document.getElementById("article-stats-meta").textContent = `📊 ${article.word_count} 字 · 预计精读 ${article.reading_time_minutes} 分钟`;
        document.getElementById("article-engine-badge").textContent =
            article.engine_used === "llm" ? "🤖 大模型深度生成" : "⚡ 内置智能分析引擎";

        const urlLink = document.getElementById("article-original-url");
        if (article.source_url) {
            urlLink.href = article.source_url;
            urlLink.classList.remove("hidden");
        } else {
            urlLink.classList.add("hidden");
        }

        document.getElementById("article-detail-title").textContent = article.title;

        // 标签与所属主题徽章
        const tagsRow = document.getElementById("article-detail-tags");
        const topicPills = (article.topics || []).map(
            (t) => `<span class="tag-badge" style="border-color:${escapeHtml(t.color)};color:${escapeHtml(t.color)};cursor:pointer;" data-jump-topic="${t.id}">🗂️ 主题：${escapeHtml(t.name)}</span>`
        );
        const tagPills = (article.tags || []).map((tg) => `<span class="tag-badge">#${escapeHtml(tg)}</span>`);
        tagsRow.innerHTML = [...topicPills, ...tagPills].join("");
        tagsRow.querySelectorAll("[data-jump-topic]").forEach((el) => {
            el.addEventListener("click", () => {
                selectTopic(Number(el.getAttribute("data-jump-topic")));
            });
        });

        // 收藏与阅读状态
        const favBtn = document.getElementById("btn-toggle-favorite");
        favBtn.textContent = article.is_favorite ? "⭐ 已收藏" : "☆ 收藏";
        document.getElementById("select-reading-status").value = article.reading_status || "reading";

        // 渲染结构化摘要内容
        const summary = article.summary || {};
        document.getElementById("summary-tldr-text").textContent =
            summary.one_sentence_summary || "暂无一句话总结";

        // 1. 核心观点
        const vpList = document.getElementById("summary-viewpoints-list");
        const viewpoints = summary.core_viewpoints || [];
        vpList.innerHTML = viewpoints
            .map(
                (vp, idx) => `
            <div class="item-box">
                <div class="item-box-header">
                    <div class="item-box-title">
                        <span class="importance-badge ${vp.importance === "中" ? "medium" : ""}">重要度: ${escapeHtml(vp.importance || "高")}</span>
                        <span>${idx + 1}. ${escapeHtml(vp.title)}</span>
                    </div>
                    <button class="btn-mini" data-quote="${escapeHtml(vp.detail)}">💬 引用此观点追问</button>
                </div>
                <div class="item-box-detail">${escapeHtml(vp.detail)}</div>
            </div>
        `
            )
            .join("");

        // 2. 关键论据
        const argList = document.getElementById("summary-arguments-list");
        const args = summary.key_arguments || [];
        argList.innerHTML = args
            .map(
                (arg) => `
            <div class="item-box">
                <div class="item-box-header">
                    <div class="item-box-title">
                        <span class="logic-type-badge">${escapeHtml(arg.logic_type || "逻辑论证")}</span>
                        <span>${escapeHtml(arg.claim)}</span>
                    </div>
                    <button class="btn-mini" data-quote="${escapeHtml(arg.evidence)}">💬 质疑/追问此论据</button>
                </div>
                <div class="item-box-detail">${escapeHtml(arg.evidence)}</div>
                ${arg.quote ? `<div class="argument-quote">原文摘录：“${escapeHtml(arg.quote)}”</div>` : ""}
            </div>
        `
            )
            .join("");

        // 3. 作者态度与立场审视
        const stance = summary.author_stance || {};
        const objScore = Number(stance.objectivity_score || 80);
        document.getElementById("summary-stance-box").innerHTML = `
            <div class="stance-grid">
                <div class="stance-item">
                    <span class="stance-label">整体行文基调</span>
                    <strong>${escapeHtml(stance.overall_tone || "理性实证")}</strong>
                </div>
                <div class="stance-item">
                    <span class="stance-label">论述客观度评估 (${objScore}/100)</span>
                    <div class="objectivity-meter">
                        <div class="objectivity-fill" style="width:${objScore}%"></div>
                    </div>
                </div>
                <div class="stance-item full-width">
                    <span class="stance-label">核心立场倾向</span>
                    <div class="item-box-detail">${escapeHtml(stance.stance_description || "")}</div>
                </div>
                <div class="stance-item full-width bias-box">
                    <span class="stance-label">⚠️ 潜在视角局限与隐含假设 (Critical Blindspots)</span>
                    <div class="item-box-detail">${escapeHtml(stance.potential_bias || "")}</div>
                </div>
                <div class="stance-item full-width">
                    <span class="stance-label">🎯 最适合阅读的目标受众</span>
                    <div class="item-box-detail">${escapeHtml(stance.target_audience || "")}</div>
                </div>
            </div>
        `;

        // 4. 可行动洞察
        const insList = document.getElementById("summary-insights-list");
        const insights = summary.actionable_insights || [];
        insList.innerHTML = insights
            .map(
                (ins) => `
            <div class="item-box">
                <div class="item-box-header">
                    <div class="item-box-title">
                        <span class="priority-badge">${escapeHtml(ins.priority || "高优先级")}</span>
                        <span>${escapeHtml(ins.action)}</span>
                    </div>
                    <button class="btn-mini" data-quote="${escapeHtml(ins.scenario)}" data-default-q="如何把这条行动洞察拆解成更具体的执行清单？">💬 追问落地细节</button>
                </div>
                <div class="item-box-detail"><strong>具体场景与做法：</strong>${escapeHtml(ins.scenario)}</div>
                <div class="item-box-detail" style="margin-top:4px;"><strong>预期收益：</strong>${escapeHtml(ins.expected_outcome)}</div>
            </div>
        `
            )
            .join("");

        // 5. 核心概念与术语表
        const conceptsGrid = document.getElementById("summary-concepts-grid");
        const concepts = summary.key_concepts || [];
        conceptsGrid.innerHTML = concepts
            .map(
                (c) => `
            <div class="concept-card">
                <div class="concept-term">📌 ${escapeHtml(c.term)}</div>
                <div class="concept-def">${escapeHtml(c.definition)}</div>
            </div>
        `
            )
            .join("");

        // 绑定所有卡片上的「引用追问」按钮
        document.querySelectorAll("#panel-article-summary [data-quote]").forEach((btn) => {
            btn.addEventListener("click", () => {
                const quote = btn.getAttribute("data-quote");
                const defaultQ = btn.getAttribute("data-default-q") || "这个观点或论据有什么潜在漏洞？与相关理论有什么联系？";
                setQuotedText(quote, defaultQ);
            });
        });

        // 渲染原文面板与个人批注面板
        document.getElementById("article-raw-content-body").innerHTML = renderMarkdown(article.raw_content || "");
        document.getElementById("textarea-user-notes").value = article.user_notes || "";

        // 渲染右侧追问面板
        renderQAPanelForArticle(article);
    }

    // ======================= 5. 多文章「主题」对比详情渲染 =======================
    async function selectTopic(topicId) {
        state.mode = "topics";
        updateSidebarModeUI();
        clearQuotedText();

        const detail = await apiFetch(`/api/topics/${topicId}`);
        state.currentTopic = detail;
        renderTopicDetailView(detail);
        renderTopicHistoryList();
    }

    function renderTopicDetailView(topic) {
        document.getElementById("workspace-empty-state").classList.add("hidden");
        document.getElementById("article-workspace-view").classList.add("hidden");
        document.getElementById("topic-workspace-view").classList.remove("hidden");

        document.getElementById("topic-color-indicator").style.background = topic.color || "#4f46e5";
        document.getElementById("topic-article-count-meta").textContent = `📚 共收录 ${topic.article_count} 篇对比文章`;
        const comp = topic.comparison || {};
        document.getElementById("topic-engine-badge").textContent =
            comp.engine_used === "llm" ? "🤖 大模型跨篇综述" : "⚡ 内置多文档对比引擎";

        document.getElementById("topic-detail-title").textContent = topic.name;
        document.getElementById("topic-detail-desc").textContent =
            topic.description || "聚合多篇相关文献，横向解构核心共识、关键分歧与视角互补关系。";
        document.getElementById("topic-included-count").textContent = (topic.articles || []).length;

        // 渲染收录的文章卡片条
        const strip = document.getElementById("topic-articles-strip");
        const articles = topic.articles || [];
        if (articles.length === 0) {
            strip.innerHTML = `<div class="qa-empty-placeholder">本主题尚未添加文章，请点击上方「➕ 管理收录文章」勾选需要对比的文章。</div>`;
        } else {
            strip.innerHTML = articles
                .map(
                    (a) => `
                <div class="topic-article-chip-card">
                    <div class="topic-article-chip-title" data-open-article="${a.id}">
                        📖 《${escapeHtml(a.title)}》
                    </div>
                    <div class="history-card-summary">${escapeHtml(a.one_sentence_summary || "")}</div>
                    <div class="topic-article-chip-footer">
                        <span>${escapeHtml(a.author || a.site_name || "未知来源")} · ${a.word_count} 字</span>
                        <button class="btn-mini" data-remove-from-topic="${a.id}" title="从本主题移除此文">移除</button>
                    </div>
                </div>
            `
                )
                .join("");

            strip.querySelectorAll("[data-open-article]").forEach((el) => {
                el.addEventListener("click", () => {
                    selectArticle(Number(el.getAttribute("data-open-article")));
                });
            });

            strip.querySelectorAll("[data-remove-from-topic]").forEach((btn) => {
                btn.addEventListener("click", async () => {
                    const aid = Number(btn.getAttribute("data-remove-from-topic"));
                    await apiFetch(`/api/topics/${topic.id}/articles/${aid}`, { method: "DELETE" });
                    showToast("已从主题中移除该文章", "info");
                    await selectTopic(topic.id);
                    await refreshStatsAndSidebar();
                });
            });
        }

        // 渲染对比报告各模块
        const compContainer = document.getElementById("topic-comparison-container");
        if (!comp || !comp.overview) {
            compContainer.innerHTML = `
                <div class="summary-card" style="text-align:center;padding:36px;">
                    <h3>⚡ 尚未生成多文章对比总结</h3>
                    <p style="color:var(--text-secondary);margin:10px 0 18px;">点击左上角「生成 / 刷新多文章对比总结」按钮，AI 将自动对比本主题下所有文章的共识、分歧与方法论矩阵。</p>
                </div>
            `;
        } else {
            document.getElementById("topic-overview-text").textContent = comp.overview || "";

            // 共识点
            document.getElementById("topic-consensus-list").innerHTML = (comp.consensus_points || [])
                .map(
                    (cp) => `
                <div class="item-box">
                    <div class="item-box-header">
                        <div class="item-box-title">🤝 ${escapeHtml(cp.point)}</div>
                    </div>
                    <div class="item-box-detail">${escapeHtml(cp.detail)}</div>
                </div>
            `
                )
                .join("");

            // 分歧与张力
            document.getElementById("topic-disagreements-list").innerHTML = (comp.disagreements || [])
                .map(
                    (dis) => `
                <div class="item-box">
                    <div class="item-box-header">
                        <div class="item-box-title">⚡ ${escapeHtml(dis.dimension)}</div>
                    </div>
                    <div class="item-box-detail">${escapeHtml(dis.conflict_summary)}</div>
                    <div class="disagreement-positions">
                        ${(dis.positions || [])
                            .map(
                                (pos) => `
                            <div class="position-card">
                                <div class="position-article-name">📄 《${escapeHtml(pos.article_title)}》</div>
                                <div>${escapeHtml(pos.stance)}</div>
                            </div>
                        `
                            )
                            .join("")}
                    </div>
                </div>
            `
                )
                .join("");

            // 多维对比矩阵表
            document.getElementById("topic-matrix-tbody").innerHTML = (comp.comparison_matrix || [])
                .map(
                    (m) => `
                <tr>
                    <td>
                        <strong>《${escapeHtml(m.article_title)}》</strong>
                        <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">${escapeHtml(m.author || "")}</div>
                    </td>
                    <td><span class="logic-type-badge">${escapeHtml(m.stance_tone)}</span></td>
                    <td>${escapeHtml(m.methodology)}</td>
                    <td>${escapeHtml(m.core_thesis)}</td>
                    <td>${escapeHtml(m.unique_value)}</td>
                    <td style="color:var(--text-secondary);">${escapeHtml(m.limitation)}</td>
                </tr>
            `
                )
                .join("");

            // 视角互补
            document.getElementById("topic-complement-box").textContent = comp.complementary_insights || "";

            // 综合行动建议
            document.getElementById("topic-actions-list").innerHTML = (comp.synthesized_actions || [])
                .map(
                    (act) => `
                <div class="item-box">
                    <div class="item-box-header">
                        <div class="item-box-title">🚀 ${escapeHtml(act.title)}</div>
                        <span class="mini-badge topic-pill">启发自：《${escapeHtml(act.source_inspiration || "")}》</span>
                    </div>
                    <div class="item-box-detail">${escapeHtml(act.detail)}</div>
                </div>
            `
                )
                .join("");
        }

        // 渲染右侧主题跨篇追问面板
        renderQAPanelForTopic(topic);
    }

    // ======================= 6. 右侧追问与思辨对话区 =======================
    function renderQAPanelForArticle(article) {
        document.getElementById("qa-panel-title").textContent = "💬 文章深度追问";
        document.getElementById("qa-panel-subtitle").textContent = `当前聚焦：《${article.title.slice(0, 22)}${article.title.length > 22 ? "…" : ""}》`;

        const customQuestions = (article.summary && article.summary.reading_questions) || [];
        const prompts = [...customQuestions.slice(0, 2), ...DEFAULT_ARTICLE_PROMPTS.slice(0, 4)];
        renderQuickPrompts(prompts);
        renderMessagesList(article.messages || []);
    }

    function renderQAPanelForTopic(topic) {
        document.getElementById("qa-panel-title").textContent = "🧭 主题跨文章追问";
        document.getElementById("qa-panel-subtitle").textContent = `跨文献探讨：「${topic.name}」(${topic.article_count} 篇)`;

        renderQuickPrompts(DEFAULT_TOPIC_PROMPTS);
        renderMessagesList(topic.messages || []);
    }

    function renderQuickPrompts(prompts) {
        const container = document.getElementById("quick-prompts-container");
        container.innerHTML = prompts
            .map((p) => `<button type="button" class="quick-prompt-chip" data-prompt="${escapeHtml(p)}">${escapeHtml(p)}</button>`)
            .join("");

        container.querySelectorAll(".quick-prompt-chip").forEach((chip) => {
            chip.addEventListener("click", () => {
                const promptText = chip.getAttribute("data-prompt").replace(/^[🔍🔗⚖️🛠️💡⚡🤝🧭]\s*/, "");
                const input = document.getElementById("input-qa-question");
                input.value = promptText;
                input.focus();
                submitQAQuestion();
            });
        });
    }

    function renderMessagesList(messages) {
        const container = document.getElementById("qa-messages-list");
        if (!messages || messages.length === 0) {
            container.innerHTML = `
                <div class="qa-empty-placeholder">
                    <p>💡 <strong>批判性阅读从提问开始</strong></p>
                    <p style="margin-top:6px;">点击上方快捷问题，或点击左侧任意观点旁边的「引用追问」，检验作者的逻辑漏洞、探讨与经典理论的关系。</p>
                </div>
            `;
            return;
        }

        container.innerHTML = messages
            .map((msg) => {
                if (msg.role === "user") {
                    return `
                    <div class="qa-message user">
                        ${msg.quoted_text ? `<div class="qa-msg-quote">📌 引用：“${escapeHtml(msg.quoted_text.slice(0, 140))}”</div>` : ""}
                        <div>${escapeHtml(msg.content)}</div>
                    </div>
                `;
                }
                return `
                <div class="qa-message assistant">
                    ${renderMarkdown(msg.content)}
                </div>
            `;
            })
            .join("");

        container.scrollTop = container.scrollHeight;
    }

    function setQuotedText(text, suggestedQuestion = "") {
        if (!text || !text.trim()) return;
        state.quotedText = text.trim();
        document.getElementById("qa-quoted-preview").textContent = state.quotedText;
        document.getElementById("qa-quoted-bar").classList.remove("hidden");
        const input = document.getElementById("input-qa-question");
        if (suggestedQuestion && !input.value.trim()) {
            input.value = suggestedQuestion;
        }
        input.focus();
    }

    function clearQuotedText() {
        state.quotedText = null;
        document.getElementById("qa-quoted-preview").textContent = "";
        document.getElementById("qa-quoted-bar").classList.add("hidden");
    }

    async function submitQAQuestion(e) {
        if (e) e.preventDefault();
        const input = document.getElementById("input-qa-question");
        const question = input.value.trim();
        if (!question) {
            showToast("请输入你想追问的问题", "error");
            return;
        }

        const submitBtn = document.getElementById("btn-submit-qa");
        submitBtn.disabled = true;
        submitBtn.textContent = "思考中...";

        try {
            if (state.mode === "articles" && state.currentArticle) {
                const resp = await apiFetch(`/api/articles/${state.currentArticle.id}/ask`, {
                    method: "POST",
                    body: JSON.stringify({
                        question,
                        quoted_text: state.quotedText,
                    }),
                });
                state.currentArticle.messages = state.currentArticle.messages || [];
                state.currentArticle.messages.push(resp.user_message, resp.assistant_message);
                renderMessagesList(state.currentArticle.messages);
            } else if (state.mode === "topics" && state.currentTopic) {
                const resp = await apiFetch(`/api/topics/${state.currentTopic.id}/ask`, {
                    method: "POST",
                    body: JSON.stringify({ question }),
                });
                state.currentTopic.messages = state.currentTopic.messages || [];
                state.currentTopic.messages.push(resp.user_message, resp.assistant_message);
                renderMessagesList(state.currentTopic.messages);
            }
            input.value = "";
            clearQuotedText();
            await refreshStatsAndSidebar();
        } catch (err) {
            showToast(err.message, "error");
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = "发送追问 ↵";
        }
    }

    // ======================= 7. 弹窗与事件绑定初始化 =======================
    function openModal(id) {
        document.getElementById(id).classList.remove("hidden");
    }

    function closeModal(id) {
        document.getElementById(id).classList.add("hidden");
    }

    function updateSidebarModeUI() {
        const isArticles = state.mode === "articles";
        document.getElementById("tab-mode-articles").classList.toggle("active", isArticles);
        document.getElementById("tab-mode-topics").classList.toggle("active", !isArticles);
        document.getElementById("sidebar-articles-panel").classList.toggle("hidden", !isArticles);
        document.getElementById("sidebar-topics-panel").classList.toggle("hidden", isArticles);
    }

    function switchArticleTab(tabName) {
        state.activeTab = tabName;
        document.getElementById("tab-btn-summary").classList.toggle("active", tabName === "summary");
        document.getElementById("tab-btn-original").classList.toggle("active", tabName === "original");
        document.getElementById("tab-btn-notes").classList.toggle("active", tabName === "notes");

        document.getElementById("panel-article-summary").classList.toggle("hidden", tabName !== "summary");
        document.getElementById("panel-article-original").classList.toggle("hidden", tabName !== "original");
        document.getElementById("panel-article-notes").classList.toggle("hidden", tabName !== "notes");
    }

    async function openImportArticleModal() {
        // 加载示例按钮与主题复选框
        if (state.samples.length === 0) {
            const sampleResp = await apiFetch("/api/articles/samples");
            state.samples = sampleResp.samples || [];
        }

        const sampleContainer = document.getElementById("import-sample-buttons");
        sampleContainer.innerHTML = state.samples
            .map(
                (s, idx) =>
                    `<button type="button" class="btn-mini" data-sample-idx="${idx}">📄 示例 ${idx + 1}：${escapeHtml(s.title.slice(0, 14))}…</button>`
            )
            .join("");

        sampleContainer.querySelectorAll("[data-sample-idx]").forEach((btn) => {
            btn.addEventListener("click", () => {
                const sample = state.samples[Number(btn.getAttribute("data-sample-idx"))];
                if (!sample) return;
                setImportSourceTab("text");
                document.getElementById("input-import-title").value = sample.title;
                document.getElementById("input-import-author").value = sample.author;
                document.getElementById("input-import-text").value = sample.raw_text;
                showToast("已填入示例文章内容，点击右下角按钮即可解析！", "info");
            });
        });

        // 渲染主题多选框
        const topicBoxes = document.getElementById("import-topics-checkboxes");
        if (state.topics.length === 0) {
            topicBoxes.innerHTML = `<span class="form-hint">暂无已创建的主题</span>`;
        } else {
            topicBoxes.innerHTML = state.topics
                .map(
                    (tp) => `
                <label class="checkbox-pill">
                    <input type="checkbox" name="import_topic_id" value="${tp.id}" />
                    <span>🗂️ ${escapeHtml(tp.name)}</span>
                </label>
            `
                )
                .join("");
        }

        openModal("modal-import-article");
    }

    function setImportSourceTab(sourceType) {
        document.getElementById("import-source-type").value = sourceType;
        document.querySelectorAll(".import-tab").forEach((btn) => {
            btn.classList.toggle("active", btn.getAttribute("data-source-type") === sourceType);
        });

        document.getElementById("group-import-url").classList.toggle("hidden", sourceType !== "url");
        document.getElementById("group-import-file").classList.toggle("hidden", sourceType !== "file");

        const textLabel = document.getElementById("label-import-text");
        if (sourceType === "url") {
            textLabel.innerHTML = `备用正文内容（选填：若目标链接反爬限制无法直接抓取，可在此粘贴正文兜底）`;
        } else {
            textLabel.innerHTML = `文章正文内容 <span class="required">*</span>`;
        }
    }

    function openTopicModal(editTopic = null) {
        document.getElementById("modal-topic-title").textContent = editTopic
            ? `🗂️ 管理对比主题：${editTopic.name}`
            : "🗂️ 创建多文章对比「主题」";
        document.getElementById("input-topic-edit-id").value = editTopic ? editTopic.id : "";
        document.getElementById("input-topic-name").value = editTopic ? editTopic.name : "";
        document.getElementById("input-topic-desc").value = editTopic ? editTopic.description || "" : "";
        document.getElementById("input-topic-color").value = editTopic ? editTopic.color || "#4f46e5" : "#4f46e5";

        const selectedIds = new Set(
            editTopic && editTopic.articles ? editTopic.articles.map((a) => a.id) : []
        );

        const listEl = document.getElementById("topic-modal-article-list");
        if (state.articles.length === 0) {
            listEl.innerHTML = `<div class="form-hint">当前历史库暂无文章，请先导入文章。</div>`;
        } else {
            listEl.innerHTML = state.articles
                .map(
                    (a) => `
                <label class="selector-row">
                    <input type="checkbox" name="topic_article_id" value="${a.id}" ${selectedIds.has(a.id) ? "checked" : ""} />
                    <div>
                        <div style="font-weight:600;">《${escapeHtml(a.title)}》</div>
                        <div style="font-size:11.5px;color:var(--text-muted);">${escapeHtml(a.author || a.site_name || "")} · ${a.word_count} 字</div>
                    </div>
                </label>
            `
                )
                .join("");
        }

        openModal("modal-topic-form");
    }

    async function openAssignTopicModal() {
        if (!state.currentArticle) return;
        const currentTopicIds = new Set((state.currentArticle.topics || []).map((t) => t.id));
        const container = document.getElementById("assign-topic-list-container");

        if (state.topics.length === 0) {
            container.innerHTML = `<div class="form-hint">暂无对比主题，请点击下方「＋ 新建主题」</div>`;
        } else {
            container.innerHTML = state.topics
                .map(
                    (tp) => `
                <label class="selector-row">
                    <input type="checkbox" data-toggle-topic="${tp.id}" ${currentTopicIds.has(tp.id) ? "checked" : ""} />
                    <div>
                        <div style="font-weight:600;">🗂️ ${escapeHtml(tp.name)}</div>
                        <div style="font-size:11.5px;color:var(--text-muted);">当前包含 ${tp.article_count} 篇文章</div>
                    </div>
                </label>
            `
                )
                .join("");

            container.querySelectorAll("[data-toggle-topic]").forEach((chk) => {
                chk.addEventListener("change", async () => {
                    const tid = Number(chk.getAttribute("data-toggle-topic"));
                    if (chk.checked) {
                        await apiFetch(`/api/topics/${tid}/articles`, {
                            method: "POST",
                            body: JSON.stringify({ article_id: state.currentArticle.id }),
                        });
                        showToast("已将该文章加入主题", "success");
                    } else {
                        await apiFetch(`/api/topics/${tid}/articles/${state.currentArticle.id}`, {
                            method: "DELETE",
                        });
                        showToast("已将该文章从主题移出", "info");
                    }
                    await selectArticle(state.currentArticle.id);
                    await refreshStatsAndSidebar();
                });
            });
        }

        openModal("modal-assign-article-topic");
    }

    async function openLLMSettingsModal() {
        const cfg = await apiFetch("/api/system/llm-config");
        document.getElementById("select-llm-provider").value = cfg.provider || "auto";
        document.getElementById("input-llm-base-url").value = cfg.base_url || "https://api.openai.com/v1";
        document.getElementById("input-llm-model").value = cfg.model || "gpt-4o-mini";
        document.getElementById("input-llm-temp").value = cfg.temperature ?? 0.3;
        document.getElementById("input-llm-api-key").value = "";
        document.getElementById("current-key-status").textContent = cfg.has_api_key
            ? `(当前已配置 Key: ${cfg.api_key_masked}，留空则保持不变)`
            : "(当前未配置 API Key，默认使用内置智能分析引擎)";
        openModal("modal-llm-settings");
    }

    function bindEvents() {
        // 关闭弹窗通用按钮
        document.querySelectorAll("[data-close-modal]").forEach((btn) => {
            btn.addEventListener("click", () => {
                closeModal(btn.getAttribute("data-close-modal"));
            });
        });

        // 顶部按钮
        document.getElementById("btn-open-import-modal").addEventListener("click", openImportArticleModal);
        document.getElementById("btn-empty-import").addEventListener("click", openImportArticleModal);
        document.getElementById("btn-open-topic-modal").addEventListener("click", () => openTopicModal(null));
        document.getElementById("btn-sidebar-new-topic").addEventListener("click", () => openTopicModal(null));
        document.getElementById("btn-open-settings-modal").addEventListener("click", openLLMSettingsModal);

        // 左侧栏模式切换
        document.getElementById("tab-mode-articles").addEventListener("click", () => {
            state.mode = "articles";
            updateSidebarModeUI();
            if (state.currentArticle) {
                renderArticleDetailView(state.currentArticle);
            } else if (state.articles.length > 0) {
                selectArticle(state.articles[0].id);
            }
        });

        document.getElementById("tab-mode-topics").addEventListener("click", () => {
            state.mode = "topics";
            updateSidebarModeUI();
            if (state.currentTopic) {
                renderTopicDetailView(state.currentTopic);
            } else if (state.topics.length > 0) {
                selectTopic(state.topics[0].id);
            }
        });

        // 搜索框与状态筛选
        let searchTimer = null;
        document.getElementById("input-article-search").addEventListener("input", (e) => {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(() => {
                state.filters.search = e.target.value.trim();
                loadArticlesList();
            }, 220);
        });

        document.querySelectorAll("#article-status-filters .filter-chip").forEach((chip) => {
            chip.addEventListener("click", () => {
                document.querySelectorAll("#article-status-filters .filter-chip").forEach((c) => c.classList.remove("active"));
                chip.classList.add("active");
                state.filters.status = chip.getAttribute("data-filter");
                loadArticlesList();
            });
        });

        // 中间栏子标签页切换
        ["summary", "original", "notes"].forEach((tab) => {
            document.getElementById(`tab-btn-${tab}`).addEventListener("click", () => switchArticleTab(tab));
        });

        // 原文划词引用追问
        document.getElementById("btn-quote-selected-text").addEventListener("click", () => {
            const sel = window.getSelection().toString().trim();
            if (!sel) {
                showToast("请先用鼠标在下方文章正文中选中一段文字", "info");
                return;
            }
            setQuotedText(sel, "请深入解读这段话的深层含义，并分析它是否存在逻辑漏洞？");
            showToast("已将选中文字添加至右侧追问引用框", "success");
        });

        // 收藏切换
        document.getElementById("btn-toggle-favorite").addEventListener("click", async () => {
            if (!state.currentArticle) return;
            const updated = await apiFetch(`/api/articles/${state.currentArticle.id}`, {
                method: "PATCH",
                body: JSON.stringify({ is_favorite: !state.currentArticle.is_favorite }),
            });
            state.currentArticle = updated;
            renderArticleDetailView(updated);
            await refreshStatsAndSidebar();
            showToast(updated.is_favorite ? "已加入星标收藏" : "已取消收藏", "success");
        });

        // 阅读状态切换
        document.getElementById("select-reading-status").addEventListener("change", async (e) => {
            if (!state.currentArticle) return;
            const updated = await apiFetch(`/api/articles/${state.currentArticle.id}`, {
                method: "PATCH",
                body: JSON.stringify({ reading_status: e.target.value }),
            });
            state.currentArticle = updated;
            await loadArticlesList();
            showToast("阅读状态已更新", "success");
        });

        // 归入主题按钮
        document.getElementById("btn-assign-topic").addEventListener("click", openAssignTopicModal);
        document.getElementById("btn-assign-create-new-topic").addEventListener("click", () => {
            closeModal("modal-assign-article-topic");
            openTopicModal(null);
        });

        // 重新生成摘要
        document.getElementById("btn-regenerate-summary").addEventListener("click", async () => {
            if (!state.currentArticle) return;
            const btn = document.getElementById("btn-regenerate-summary");
            btn.disabled = true;
            btn.textContent = "⏳ 生成中...";
            try {
                const updated = await apiFetch(`/api/articles/${state.currentArticle.id}/regenerate`, {
                    method: "POST",
                });
                state.currentArticle = updated;
                renderArticleDetailView(updated);
                showToast("已重新生成结构化摘要！", "success");
            } catch (err) {
                showToast(err.message, "error");
            } finally {
                btn.disabled = false;
                btn.textContent = "🔄 重生成";
            }
        });

        // 复制摘要
        document.getElementById("btn-copy-summary").addEventListener("click", async () => {
            if (!state.currentArticle) return;
            const data = await apiFetch(`/api/articles/${state.currentArticle.id}/export`);
            if (navigator.clipboard && data.markdown) {
                await navigator.clipboard.writeText(data.markdown);
                showToast("已将完整 Markdown 读书笔记复制到剪贴板！", "success");
            }
        });

        // 导出单篇文章 Markdown
        document.getElementById("btn-export-article").addEventListener("click", () => {
            if (!state.currentArticle) return;
            window.open(`/api/articles/${state.currentArticle.id}/export?download=1`, "_blank");
        });

        // 删除单篇文章
        document.getElementById("btn-delete-article").addEventListener("click", async () => {
            if (!state.currentArticle) return;
            if (!window.confirm(`确定要删除《${state.currentArticle.title}》吗？`)) return;
            await apiFetch(`/api/articles/${state.currentArticle.id}`, { method: "DELETE" });
            showToast("文章已删除", "info");
            state.currentArticle = null;
            await refreshStatsAndSidebar();
            if (state.articles.length > 0) {
                await selectArticle(state.articles[0].id);
            } else {
                document.getElementById("article-workspace-view").classList.add("hidden");
                document.getElementById("workspace-empty-state").classList.remove("hidden");
            }
        });

        // 保存个人阅读批注
        document.getElementById("btn-save-user-notes").addEventListener("click", async () => {
            if (!state.currentArticle) return;
            const notes = document.getElementById("textarea-user-notes").value;
            const updated = await apiFetch(`/api/articles/${state.currentArticle.id}`, {
                method: "PATCH",
                body: JSON.stringify({ user_notes: notes }),
            });
            state.currentArticle = updated;
            showToast("个人阅读批注已保存！", "success");
        });

        // 主题对比操作按钮
        document.getElementById("btn-run-topic-compare").addEventListener("click", async () => {
            if (!state.currentTopic) return;
            const btn = document.getElementById("btn-run-topic-compare");
            btn.disabled = true;
            btn.textContent = "⏳ 正在横向对比多篇文献...";
            try {
                const updated = await apiFetch(`/api/topics/${state.currentTopic.id}/compare`, {
                    method: "POST",
                });
                state.currentTopic = updated;
                renderTopicDetailView(updated);
                await refreshStatsAndSidebar();
                showToast("多文章横向对比报告已生成！", "success");
            } catch (err) {
                showToast(err.message, "error");
            } finally {
                btn.disabled = false;
                btn.textContent = "⚡ 生成 / 刷新多文章对比总结";
            }
        });

        document.getElementById("btn-manage-topic-articles").addEventListener("click", () => {
            if (!state.currentTopic) return;
            openTopicModal(state.currentTopic);
        });

        document.getElementById("btn-export-topic").addEventListener("click", () => {
            if (!state.currentTopic) return;
            window.open(`/api/topics/${state.currentTopic.id}/export?download=1`, "_blank");
        });

        document.getElementById("btn-delete-topic").addEventListener("click", async () => {
            if (!state.currentTopic) return;
            if (!window.confirm(`确定要删除主题「${state.currentTopic.name}」吗？（不会删除收录的文章本身）`)) return;
            await apiFetch(`/api/topics/${state.currentTopic.id}`, { method: "DELETE" });
            showToast("主题已删除", "info");
            state.currentTopic = null;
            await refreshStatsAndSidebar();
            if (state.topics.length > 0) {
                await selectTopic(state.topics[0].id);
            } else if (state.articles.length > 0) {
                await selectArticle(state.articles[0].id);
            }
        });

        // 追问表单提交与快捷键
        document.getElementById("form-qa-ask").addEventListener("submit", submitQAQuestion);
        document.getElementById("input-qa-question").addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submitQAQuestion();
            }
        });
        document.getElementById("btn-clear-quote").addEventListener("click", clearQuotedText);

        document.getElementById("btn-clear-chat").addEventListener("click", async () => {
            if (state.mode === "articles" && state.currentArticle) {
                await apiFetch(`/api/articles/${state.currentArticle.id}/messages`, { method: "DELETE" });
                state.currentArticle.messages = [];
                renderMessagesList([]);
                showToast("对话记录已清空", "info");
            }
        });

        // 导入文章弹窗内交互
        document.querySelectorAll(".import-tab").forEach((btn) => {
            btn.addEventListener("click", () => {
                setImportSourceTab(btn.getAttribute("data-source-type"));
            });
        });

        document.getElementById("input-import-file").addEventListener("change", (e) => {
            const file = e.target.files && e.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = (ev) => {
                document.getElementById("input-import-text").value = ev.target.result || "";
                if (!document.getElementById("input-import-title").value) {
                    document.getElementById("input-import-title").value = file.name.replace(/\.(txt|md|markdown)$/i, "");
                }
            };
            reader.readAsText(file, "utf-8");
        });

        document.getElementById("form-import-article").addEventListener("submit", async (e) => {
            e.preventDefault();
            const sourceType = document.getElementById("import-source-type").value;
            const url = document.getElementById("input-import-url").value.trim();
            const title = document.getElementById("input-import-title").value.trim();
            const author = document.getElementById("input-import-author").value.trim();
            const rawText = document.getElementById("input-import-text").value.trim();
            const topicIds = Array.from(document.querySelectorAll("input[name='import_topic_id']:checked")).map((el) =>
                Number(el.value)
            );

            const submitBtn = document.getElementById("btn-submit-import");
            submitBtn.disabled = true;
            submitBtn.textContent = "⏳ 正在智能解析文章并提炼结构化摘要...";

            try {
                const created = await apiFetch("/api/articles", {
                    method: "POST",
                    body: JSON.stringify({
                        source_type: sourceType,
                        url,
                        title,
                        author,
                        raw_text: rawText,
                        topic_ids: topicIds,
                    }),
                });
                closeModal("modal-import-article");
                document.getElementById("form-import-article").reset();
                showToast(`《${created.title}》解析完成！`, "success");
                await refreshStatsAndSidebar();
                await selectArticle(created.id);
            } catch (err) {
                showToast(err.message, "error");
            } finally {
                submitBtn.disabled = false;
                submitBtn.textContent = "🚀 开始智能解析并生成摘要";
            }
        });

        // 创建/保存主题表单提交
        document.getElementById("form-topic-save").addEventListener("submit", async (e) => {
            e.preventDefault();
            const editId = document.getElementById("input-topic-edit-id").value;
            const name = document.getElementById("input-topic-name").value.trim();
            const description = document.getElementById("input-topic-desc").value.trim();
            const color = document.getElementById("input-topic-color").value;
            const articleIds = Array.from(document.querySelectorAll("input[name='topic_article_id']:checked")).map(
                (el) => Number(el.value)
            );

            const btn = document.getElementById("btn-submit-topic");
            btn.disabled = true;
            btn.textContent = "⏳ 正在保存并生成多文章对比总结...";

            try {
                let savedTopic;
                if (editId) {
                    savedTopic = await apiFetch(`/api/topics/${editId}`, {
                        method: "PATCH",
                        body: JSON.stringify({
                            name,
                            description,
                            color,
                            article_ids: articleIds,
                            auto_compare: articleIds.length > 0,
                        }),
                    });
                } else {
                    savedTopic = await apiFetch("/api/topics", {
                        method: "POST",
                        body: JSON.stringify({
                            name,
                            description,
                            color,
                            article_ids: articleIds,
                            auto_compare: articleIds.length > 0,
                        }),
                    });
                }
                closeModal("modal-topic-form");
                showToast(`主题「${savedTopic.name}」已保存！`, "success");
                await refreshStatsAndSidebar();
                await selectTopic(savedTopic.id);
            } catch (err) {
                showToast(err.message, "error");
            } finally {
                btn.disabled = false;
                btn.textContent = "⚡ 保存主题并生成对比总结";
            }
        });

        // AI 引擎预设服务商按钮与保存
        document.querySelectorAll("[data-preset]").forEach((btn) => {
            btn.addEventListener("click", () => {
                const preset = LLM_PROVIDER_PRESETS[btn.getAttribute("data-preset")];
                if (!preset) return;
                document.getElementById("input-llm-base-url").value = preset.base_url;
                document.getElementById("input-llm-model").value = preset.model;
                showToast(`已填入 ${btn.textContent} 默认接口地址与模型`, "info");
            });
        });

        document.getElementById("form-llm-settings").addEventListener("submit", async (e) => {
            e.preventDefault();
            const provider = document.getElementById("select-llm-provider").value;
            const baseUrl = document.getElementById("input-llm-base-url").value.trim();
            const model = document.getElementById("input-llm-model").value.trim();
            const apiKey = document.getElementById("input-llm-api-key").value.trim();
            const temperature = parseFloat(document.getElementById("input-llm-temp").value) || 0.3;

            try {
                await apiFetch("/api/system/llm-config", {
                    method: "PUT",
                    body: JSON.stringify({
                        provider,
                        base_url: baseUrl,
                        model,
                        api_key: apiKey,
                        keep_existing_key: apiKey === "",
                        temperature,
                    }),
                });
                closeModal("modal-llm-settings");
                await refreshStatsAndSidebar();
                showToast("AI 引擎配置已保存并立即生效！", "success");
            } catch (err) {
                showToast(err.message, "error");
            }
        });

        // 恢复/加载演示数据
        const handleSeedDemo = async () => {
            const resp = await apiFetch("/api/system/seed", { method: "POST" });
            showToast(`已加载 ${resp.articles_created} 篇示例文章与对比主题！`, "success");
            await refreshStatsAndSidebar();
            if (state.articles.length > 0) {
                await selectArticle(state.articles[0].id);
            }
        };
        document.getElementById("btn-restore-demo").addEventListener("click", handleSeedDemo);
        document.getElementById("btn-empty-seed").addEventListener("click", handleSeedDemo);
    }

    // ======================= 8. 启动入口 =======================
    async function initApp() {
        bindEvents();
        try {
            await refreshStatsAndSidebar();
            if (state.articles.length > 0) {
                await selectArticle(state.articles[0].id);
            } else {
                document.getElementById("article-workspace-view").classList.add("hidden");
                document.getElementById("workspace-empty-state").classList.remove("hidden");
            }
        } catch (err) {
            showToast(`初始化失败: ${err.message}`, "error");
        }
    }

    document.addEventListener("DOMContentLoaded", initApp);
})();
