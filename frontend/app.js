/** 读懂 — no build step. All article/model content is inserted as text, never HTML. */
const $ = (selector, root = document) => root.querySelector(selector);
const main = $('#main');
const modal = $('#modal');
const state = { topics: [], config: null, article: null, route: null, renderId: 0, page: 0, query: '', favorite: false };
let token = '';
try { token = localStorage.getItem('reading-access-token') || ''; } catch { /* Storage may be unavailable. */ }

const paths = {
  book: '<path d="M12 6c-3-3-7-3-9-2v15c3-1 6-1 9 2 3-3 6-3 9-2V4c-2-1-6-1-9 2Zm0 0v15"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  folder: '<path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/>',
  star: '<path d="m12 3 2.8 5.8 6.4.9-4.6 4.5 1.1 6.4-5.7-3-5.7 3 1.1-6.4-4.6-4.5 6.4-.9L12 3Z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
  back: '<path d="M19 12H5m6-6-6 6 6 6"/>',
  spark: '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Zm8 0v4m-2-2h4"/>',
  link: '<path d="m9 15 6-6m-6-2 2-2a5 5 0 0 1 7 7l-2 2m-1 3-2 2a5 5 0 0 1-7-7l2-2"/>',
  text: '<path d="M4 4h16M12 4v16M8 20h8M4 4v3m16-3v3"/>',
  check: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  upload: '<path d="M12 16V4m-5 5 5-5 5 5M4 16v5h16v-5"/>',
  settings: '<path d="m10 3-1 3-3 1-3-1-1 4 3 2-1 3-2 2 3 3 3-1 3 1 1 3 4-1 1-3 3-1 3 1 1-4-3-2 1-3 2-2-3-3-3 1-3-1-1-3-4 1Z" transform="translate(0 -1) scale(.95)"/><circle cx="12" cy="12" r="3"/>',
  trash: '<path d="M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7"/>',
  edit: '<path d="m16 3 5 5-12 12-6 1 1-6L16 3Zm-2 2 5 5"/>',
  refresh: '<path d="M20 8a9 9 0 1 0 1 7M20 3v6h-6"/>',
  send: '<path d="m21 3-6 18-4-8-8-4 18-6ZM11 13 21 3"/>',
  chat: '<path d="M21 11a9 9 0 0 1-9 9H4l-2 2 1-8a9 9 0 1 1 18-3Z"/><path d="M8 10h8m-8 4h5"/>',
  compare: '<path d="M5 3v18M19 3v18M2 7h6m8 10h6M8 12h8m-3-3 3 3-3 3"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>',
};
function icon(name) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('fill', 'none'); svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-linecap', 'round'); svg.setAttribute('stroke-linejoin', 'round'); svg.setAttribute('aria-hidden', 'true');
  // Only constant paths from the icon map enter innerHTML.
  svg.innerHTML = paths[name] || paths.book;
  return svg;
}
function replace(node, ...children) { node.replaceChildren(...children.flat(Infinity).filter(child => child !== false && child !== null && child !== undefined)); }
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === 'class') node.className = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (key === 'text') node.textContent = value;
    else if (value !== null && value !== undefined && value !== false) node.setAttribute(key, value === true ? '' : String(value));
  }
  for (const child of children.flat(Infinity)) if (child !== null && child !== undefined && child !== false) node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  return node;
}
function button(text, action, { kind = '', symbol, title, disabled = false } = {}) {
  return el('button', { type: 'button', class: `btn ${kind}`, onclick: action, title, disabled }, symbol && icon(symbol), text);
}
function iconButton(symbol, label, action, extraClass = '') {
  return el('button', { type: 'button', class: `icon-btn ${extraClass}`, 'aria-label': label, title: label, onclick: action }, icon(symbol));
}
function toast(message, error = false) {
  const node = el('div', { class: `toast ${error ? 'error' : ''}`, role: error ? 'alert' : 'status' }, message);
  $('#toasts').append(node); setTimeout(() => node.remove(), error ? 9000 : 4500);
}
async function api(path, { method = 'GET', body, signal } = {}) {
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers['X-Access-Token'] = token;
  let response;
  try { response = await fetch(`/api${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal }); }
  catch (error) { if (error.name === 'AbortError') throw error; throw new Error('无法连接服务，请检查网络或确认后端已经启动。'); }
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    const message = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(item => item.msg).join('；') : '请求失败，请稍后重试。';
    throw new Error(response.status === 401 ? '需要访问令牌。请在左下角「连接设置」填写服务器配置的 APP_ACCESS_TOKEN。' : message);
  }
  return data;
}
async function busy(buttonNode, action, label = '处理中…') {
  if (buttonNode.disabled) return;
  const old = [...buttonNode.childNodes]; buttonNode.disabled = true; replace(buttonNode, el('span', { class: 'spinner' }), buttonNode.classList.contains('icon-btn') ? '' : label);
  try { return await action(); }
  catch (error) { toast(error.message, true); }
  finally { if (buttonNode.isConnected) { buttonNode.disabled = false; replace(buttonNode, ...old); } }
}
function date(value, withTime = false) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value || '';
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', ...(withTime ? { hour: '2-digit', minute: '2-digit' } : { year: 'numeric' }) }).format(parsed);
}
function topicName(id) { return state.topics.find(topic => topic.id === id)?.name || '未归类'; }
function articleCount(item) { return item.word_count || item.text?.length || 0; }
function countText(item) { const count = articleCount(item); return `${count.toLocaleString()} 字 · 约 ${Math.max(1, Math.ceil(count / 600))} 分钟`; }
function modeText(mode) { return mode === 'ai' ? 'AI 生成' : '本地演示'; }
function notice(message, kind = 'info') { return el('div', { class: `notice ${kind}`, role: kind === 'error' ? 'alert' : 'note' }, icon('info'), el('div', {}, message)); }
function navigate(path) { if (location.hash === `#${path}`) renderRoute(); else location.hash = path; }
function route() {
  const [name = 'library', id] = location.hash.replace(/^#\/?/, '').split('/');
  try { return { name: name || 'library', id: id ? decodeURIComponent(id) : undefined }; }
  catch { return { name: 'library' }; }
}
function sidebar() {
  const current = route();
  const nav = (label, symbol, path, active, count) => el('a', { class: `nav-link ${active ? 'active' : ''}`, href: `#/${path}`, onclick: closeMenu, 'aria-current': active ? 'page' : null }, icon(symbol), label, count !== undefined && el('span', { class: 'nav-count' }, count));
  replace($('#sidebar'), 
    el('a', { class: 'brand', href: '#/library', onclick: closeMenu }, el('span', { class: 'brand-mark' }, icon('book')), el('span', {}, el('span', { class: 'brand-name' }, '读懂'), el('span', { class: 'brand-subtitle' }, 'YOUR READING COMPANION'))),
    el('nav', { class: 'nav-group', 'aria-label': '阅读导航' },
      nav('文章库', 'grid', 'library', current.name === 'library' || current.name === 'article'),
      nav('主题空间', 'folder', 'topics', current.name === 'topics'),
      nav('我的收藏', 'star', 'favorites', current.name === 'favorites'),
      nav('阅读历史', 'clock', 'history', current.name === 'history')),
    el('div', {}, el('div', { class: 'section-label' }, '我的主题', iconButton('plus', '创建主题', () => topicDialog())),
      el('nav', { class: 'nav-group', 'aria-label': '我的主题' },
        state.topics.length ? state.topics.slice(0, 12).map(topic => el('a', { class: `nav-link topic-nav ${current.name === 'topic' && current.id === topic.id ? 'active' : ''}`, href: `#/topic/${topic.id}`, onclick: closeMenu }, el('span', { class: 'topic-dot' }), el('span', { class: 'nav-topic-name' }, topic.name), el('span', { class: 'nav-count' }, topic.article_count))) : el('p', { class: 'sidebar-note' }, '创建一个主题，把相关的文章放在一起。'))),
    el('div', { class: 'sidebar-bottom' },
      el('button', { class: 'text-button', onclick: exportBackup }, icon('download'), '导出全部数据'),
      el('button', { class: 'text-button', onclick: () => $('#import-file').click() }, icon('upload'), '导入数据备份'),
      el('button', { class: 'text-button', onclick: settingsDialog }, icon('settings'), '连接设置'),
      el('p', { class: 'sidebar-note' }, '思考比收藏更进一步。', el('br'), 'v1.0 · 私人阅读工作台')),
  );
}
function closeMenu() { $('#sidebar').classList.remove('open'); $('#menu-toggle').setAttribute('aria-expanded', 'false'); }
function pageHeader(eyebrow, title, subtitle, actions) {
  return el('div', { class: 'page-head' }, el('div', {}, el('p', { class: 'eyebrow' }, eyebrow), el('h1', {}, title), subtitle && el('p', { class: 'subtitle' }, subtitle)), actions);
}
function emptyState(title, text, actions, symbol = 'book') {
  return el('div', { class: 'empty' }, el('div', { class: 'empty-icon' }, icon(symbol)), el('h2', {}, title), el('p', {}, text), actions && el('div', { class: 'button-row' }, actions));
}
function errorPage(error) {
  replace(main, emptyState('暂时无法打开阅读空间', error.message, [button('重试', renderRoute, { kind: 'primary', symbol: 'refresh' }), button('连接设置', settingsDialog, { symbol: 'settings' })]));
}
async function refreshTopics() { state.topics = await api('/topics'); sidebar(); }
async function refreshConfig() {
  state.config = await api('/config');
  $('#mode-label').textContent = state.config.mode === 'ai' ? `AI 模式 · ${state.config.model}` : '本地演示模式';
}

/** Only a matched, still-active render may commit data to the main view. */
async function renderRoute() {
  const renderId = ++state.renderId;
  state.route = route(); state.article = null; state.page = 0; state.query = '';
  sidebar(); closeMenu();
  const labels = { library: '文章库', topics: '主题空间', topic: '主题空间', favorites: '我的收藏', history: '阅读历史', article: '文章阅读' };
  $('#page-label').textContent = labels[state.route.name] || '文章库';
  replace(main, el('div', { class: 'page-loading' }, el('span', { class: 'spinner' }), ' 正在加载…'));
  try {
    await refreshTopics();
    if (renderId !== state.renderId) return;
    if (state.route.name === 'article' && state.route.id) await showArticle(state.route.id, renderId);
    else if (state.route.name === 'topic' && state.route.id) await showTopic(state.route.id, renderId);
    else if (state.route.name === 'topics') showTopics();
    else if (state.route.name === 'history') await showHistory(renderId);
    else showLibrary(state.route.name === 'favorites', renderId);
  } catch (error) { if (renderId === state.renderId) errorPage(error); }
}

function showLibrary(favorites, renderId) {
  let tabFavorite = favorites;
  let currentPage = 0;
  let query = '';
  let searchTimer;
  let requestId = 0;
  const list = el('div');
  const allTab = el('button', { class: `tab ${favorites ? '' : 'active'}`, onclick: () => setFilter(false), 'aria-pressed': !favorites }, '全部文章');
  const favoriteTab = el('button', { class: `tab ${favorites ? 'active' : ''}`, onclick: () => setFilter(true), 'aria-pressed': favorites }, '已收藏');
  const search = el('input', { type: 'search', 'aria-label': '搜索文章标题或内容', placeholder: '搜索文章标题或内容…', oninput: event => { query = event.target.value; currentPage = 0; clearTimeout(searchTimer); searchTimer = setTimeout(load, 280); } });
  replace(main, 
    pageHeader('MY READING LIBRARY', favorites ? '我的收藏' : '我的文章库', favorites ? '把值得反复思考的文章，留在手边。' : '读过的文字，会成为思考的线索。', button('添加文章', () => addArticleDialog(), { kind: 'primary', symbol: 'plus' })),
    !favorites && el('section', { class: 'intro-banner', 'aria-label': '阅读助手简介' },
      el('div', {}, el('h2', {}, '把阅读，变成自己的见解。'), el('p', {}, '不止是读完。提炼重点，追问观点，连接不同的思考。'),
        el('div', { class: 'banner-steps' }, el('span', {}, icon('link'), '导入文章'), el('span', {}, '→'), el('span', {}, icon('spark'), '提炼与追问'), el('span', {}, '→'), el('span', {}, icon('folder'), '主题对比'))),
      el('div', { class: 'book-art', 'aria-hidden': 'true' }, el('div', { class: 'book one' }), el('div', { class: 'book two' }), el('div', { class: 'book three' }))),
    el('div', { class: 'toolbar' }, el('div', { class: 'tabs', 'aria-label': '文章筛选' }, allTab, favoriteTab), el('div', { class: 'search-box' }, icon('search'), search)), list,
  );
  function setFilter(value) {
    tabFavorite = value; currentPage = 0;
    allTab.classList.toggle('active', !value); allTab.setAttribute('aria-pressed', String(!value));
    favoriteTab.classList.toggle('active', value); favoriteTab.setAttribute('aria-pressed', String(value));
    load();
  }
  async function load() {
    const thisRequest = ++requestId;
    list.classList.add('loading-overlay');
    try {
      const params = new URLSearchParams({ limit: '24', offset: String(currentPage * 24), q: query });
      if (tabFavorite) params.set('favorite', 'true');
      const data = await api(`/articles?${params}`);
      if (renderId !== state.renderId || thisRequest !== requestId) return;
      const items = data.items;
      replace(list, items.length ? el('div', { class: 'articles-grid' }, items.map(article => articleCard(article))) : emptyState(query ? '没有找到相关文章' : tabFavorite ? '还没有收藏的文章' : '从一篇文章，开始新的思考', query ? '试试其他关键词，或清空搜索条件。' : tabFavorite ? '点击文章右上角的星标，就能把它收藏在这里。' : '粘贴链接或文章正文，获得结构化摘要，再用追问把它读得更深。', !query && !tabFavorite ? [button('导入第一篇文章', () => addArticleDialog(), { kind: 'primary', symbol: 'plus' }), button('试读两篇示例', event => createExample(event.currentTarget), { symbol: 'spark' })] : null),
        el('div', { class: 'library-meta' }, el('span', {}, `共 ${data.total} 篇${tabFavorite ? '收藏' : ''}文章`), el('span', {}, '最近更新优先')),
        data.total > 24 && pagination(currentPage, data.total, 24, next => { currentPage = next; load(); }),
      );
    } catch (error) { if (renderId === state.renderId && thisRequest === requestId) replace(list, notice(error.message, 'error'), button('重新加载', load, { symbol: 'refresh' })); }
    finally { if (thisRequest === requestId) list.classList.remove('loading-overlay'); }
  }
  load();
}
function pagination(page, total, size, onChange) {
  return el('div', { class: 'pagination' }, button('上一页', () => onChange(page - 1), { kind: 'small', disabled: page === 0 }), `${page + 1} / ${Math.ceil(total / size)}`, button('下一页', () => onChange(page + 1), { kind: 'small', disabled: (page + 1) * size >= total }));
}
function articleCard(article) {
  const favorite = iconButton('star', article.favorite ? '取消收藏' : '收藏文章', event => busy(event.currentTarget, async () => {
    const updated = await api(`/articles/${article.id}`, { method: 'PATCH', body: { favorite: !article.favorite } });
    article.favorite = updated.favorite; favorite.classList.toggle('favorite-on', article.favorite);
    favorite.setAttribute('aria-label', article.favorite ? '取消收藏' : '收藏文章');
    favorite.setAttribute('title', article.favorite ? '取消收藏' : '收藏文章');
    toast(article.favorite ? '已收藏文章' : '已取消收藏');
  }), article.favorite ? 'favorite-on' : '');
  const summary = article.summary?.core_points?.[0] || article.text || '打开文章，开始阅读与思考。';
  return el('article', { class: 'article-card' },
    el('div', { class: 'card-top' }, el('span', { class: `topic-tag ${article.topic_id ? '' : 'warm'}` }, topicName(article.topic_id)), favorite),
    el('h2', { class: 'article-title' }, el('a', { href: `#/article/${article.id}` }, article.title)),
    el('p', { class: 'card-excerpt' }, summary),
    el('div', { class: 'card-meta' }, el('span', {}, date(article.created_at)), el('span', {}, '·'), el('span', {}, countText(article))),
    el('div', { class: 'card-bottom' }, el('span', { class: 'summary-ready' }, icon(article.summary ? 'check' : 'refresh'), article.error ? '摘要待重试' : article.summary ? `${modeText(article.mode)} · 结构化摘要` : '等待生成摘要'), icon('arrow')),
  );
}

function showTopics() {
  replace(main, pageHeader('CONNECT YOUR IDEAS', '主题空间', '让不同的文章，在同一个问题下相遇。', button('创建主题', () => topicDialog(), { kind: 'primary', symbol: 'plus' })),
    state.topics.length ? el('div', { class: 'topic-grid' }, state.topics.map(topic => el('article', { class: 'topic-card' }, el('span', { class: 'topic-dot' }), el('h3', {}, el('a', { href: `#/topic/${topic.id}` }, topic.name)), el('p', {}, topic.description || '收集相关文章，发现共识与分歧。'), el('footer', {}, `${topic.article_count} 篇文章`, iconButton('edit', `编辑主题 ${topic.name}`, () => topicDialog(topic)))))) : emptyState('给好奇心，建立一个主题', '例如「人工智能与学习」「长期主义」。加入两篇以上文章后，即可生成跨文章对比。', button('创建第一个主题', () => topicDialog(), { kind: 'primary', symbol: 'plus' }), 'folder'));
}
async function showTopic(id, renderId) {
  const topic = state.topics.find(item => item.id === id);
  if (!topic) throw new Error('主题不存在或已被删除。');
  const [data, comparisons] = await Promise.all([api(`/articles?topic_id=${encodeURIComponent(id)}&limit=100&offset=0`), api(`/topics/${id}/comparisons`)]);
  if (renderId !== state.renderId) return;
  const chosen = new Set();
  const count = el('span', {}, '选择 2–8 篇文章进行对比');
  const compareButton = button('生成对比总结', event => busy(event.currentTarget, async () => {
    const selected = [...chosen];
    const checkboxes = [...articleList.querySelectorAll('input[type="checkbox"]')];
    checkboxes.forEach(node => node.disabled = true);
    try {
      const comparison = await api(`/topics/${id}/compare`, { method: 'POST', body: { article_ids: selected } });
      if (renderId !== state.renderId) return;
      comparisons.unshift(comparison); renderComparisons();
      toast('对比总结已保存'); comparisonList.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } finally { checkboxes.forEach(node => node.disabled = false); }
  }, '正在对比…'), { kind: 'primary', symbol: 'compare', disabled: true });
  const comparisonList = el('section', { class: 'compare-panel' });
  const articleList = el('div');
  let page = 0;
  let visibleData = data;
  const itemsNode = el('div');
  const pager = el('div');
  async function loadPage(next) {
    try {
      const result = await api(`/articles?topic_id=${encodeURIComponent(id)}&limit=100&offset=${next * 100}`);
      if (renderId !== state.renderId) return;
      page = next; visibleData = result; drawArticleChoices();
    } catch (error) { toast(error.message, true); }
  }
  function drawArticleChoices() {
    replace(itemsNode, visibleData.items.map(article => {
      const checkbox = el('input', { type: 'checkbox', id: `choose-${article.id}`, checked: chosen.has(article.id), onchange: event => {
        if (event.target.checked && chosen.size >= 8) { event.target.checked = false; toast('一次最多对比 8 篇文章。', true); return; }
        if (event.target.checked) chosen.add(article.id); else chosen.delete(article.id);
        count.textContent = `已选择 ${chosen.size} 篇文章 · 至少选择 2 篇`;
        compareButton.disabled = chosen.size < 2;
      } });
      return el('div', { class: 'select-row' }, checkbox, el('label', { for: `choose-${article.id}` }, article.title), el('small', {}, countText(article)), el('a', { class: 'icon-btn', href: `#/article/${article.id}`, 'aria-label': `阅读 ${article.title}` }, icon('arrow')));
    }));
    replace(pager, visibleData.total > 100 ? pagination(page, visibleData.total, 100, loadPage) : null);
  }
  function renderComparisons() {
    replace(comparisonList, el('h2', {}, '已保存的对比'), comparisons.length ? comparisons.map((comparison, index) => el('details', { class: 'comparison-card', open: index === 0 }, el('summary', {}, el('span', {}, `${comparison.article_ids.length} 篇文章 · ${modeText(comparison.mode)}`), el('span', { class: 'muted' }, date(comparison.created_at, true))), comparisonContent(comparison))) : el('p', { class: 'subtitle' }, '还没有对比总结。选择文章后，生成第一份对比。'));
  }
  drawArticleChoices(); renderComparisons();
  articleList.append(itemsNode, pager);
  replace(main, pageHeader('TOPIC WORKSPACE', topic.name, topic.description || '把文章放在一起，辨认共同点、分歧与值得验证的问题。', el('div', { class: 'topic-head-tools' }, button('编辑', () => topicDialog(topic), { symbol: 'edit' }), button('添加文章', () => addArticleDialog(id), { kind: 'primary', symbol: 'plus' }), iconButton('trash', '删除主题', async () => {
    if (!await confirmDialog('删除这个主题？', '主题和它的对比记录会被删除，文章仍保留在文章库。', '删除主题')) return;
    try { await api(`/topics/${id}`, { method: 'DELETE' }); toast('主题已删除，文章已保留'); navigate('/topics'); } catch (error) { toast(error.message, true); }
  }))),
    el('div', { class: 'compare-box' }, el('div', {}, el('h3', {}, '不同文章，同一个问题'), el('p', {}, count)), compareButton),
    !data.items.length ? emptyState('这个主题还没有文章', '添加文章，或在文章详情底部把已有文章移入当前主题。', button('添加文章', () => addArticleDialog(id), { kind: 'primary', symbol: 'plus' }), 'folder') : articleList,
    data.total > 0 && el('p', { class: 'field-hint' }, `主题共 ${data.total} 篇文章。可跨页选择；每次对比最多 8 篇。`), comparisonList);
}
function comparisonContent(comparison) {
  const result = comparison.result;
  const section = (title, items) => el('section', { class: 'compare-section' }, el('h3', {}, title), plainList(items));
  return el('div', { class: 'comparison-content' }, comparison.mode !== 'ai' && notice('这是本地规则生成的演示对比。配置模型后可获得语义级的共识与冲突分析。'), el('p', { class: 'compare-overview' }, result.overview), section('共同关注', result.common_ground), el('section', { class: 'compare-section' }, el('h3', {}, '各自的观点'), (result.differences || []).map(item => el('div', { class: 'compare-position' }, el('strong', {}, item.title), el('p', {}, item.position)))), section('分歧与冲突', result.contradictions), section('综合洞察', result.insights));
}
function plainList(items) { return el('ul', { class: 'summary-list' }, (items || []).map(text => el('li', {}, text))); }

async function showHistory(renderId) {
  let page = 0;
  const content = el('div');
  replace(main, pageHeader('YOUR READING JOURNEY', '阅读历史', '按最近更新时间，回看文章、摘要与对话的积累。', button('添加文章', () => addArticleDialog(), { kind: 'primary', symbol: 'plus' })), content);
  async function load() {
    const data = await api(`/articles?limit=30&offset=${page * 30}`);
    if (renderId !== state.renderId) return;
    replace(content, data.items.length ? el('div', { class: 'history-list' }, data.items.map(article => el('div', { class: 'history-row' }, el('time', { class: 'history-date', datetime: article.updated_at }, date(article.updated_at, true)), el('div', { class: 'history-content' }, el('a', { href: `#/article/${article.id}` }, article.title), el('p', {}, `${topicName(article.topic_id)} · ${countText(article)} · ${modeText(article.mode)}`)), icon('arrow')))) : emptyState('阅读的足迹，从这里开始', '添加文章之后，就能在这里找到历史记录。', button('添加文章', () => addArticleDialog(), { kind: 'primary', symbol: 'plus' }), 'clock'), data.total > 30 && pagination(page, data.total, 30, next => { page = next; load().catch(error => toast(error.message, true)); }));
  }
  await load();
}

function citedText(tag, text, className = '') {
  const node = el(tag, { class: className });
  const parts = String(text ?? '').split(/(\[p\d+\])/g);
  for (const part of parts) {
    const match = part.match(/^\[p(\d+)\]$/);
    if (match) node.append(el('button', { type: 'button', class: 'citation', onclick: () => showParagraph(Number(match[1])), title: `查看原文段落 ${match[1]}` }, part));
    else node.append(document.createTextNode(part));
  }
  return node;
}
let setArticleTab = null;
function showParagraph(index) {
  if (!state.article) return;
  setArticleTab?.('source');
  const paragraph = $(`#p${index}`);
  if (paragraph) {
    paragraph.scrollIntoView({ behavior: 'smooth', block: 'center' });
    paragraph.classList.add('source-highlight'); setTimeout(() => paragraph.classList.remove('source-highlight'), 2200);
  } else toast('此段落编号不在原文中，请核对模型引用。', true);
}
async function showArticle(id, renderId) {
  const [article, messages] = await Promise.all([api(`/articles/${id}`), api(`/articles/${id}/messages`)]);
  if (renderId !== state.renderId) return;
  state.article = article;
  const body = el('div', { class: 'article-body' });
  const summaryTab = el('button', { class: 'tab active', onclick: () => setTab('summary') }, '结构化摘要');
  const sourceTab = el('button', { class: 'tab', onclick: () => setTab('source') }, '原文内容');
  function setTab(tab) {
    summaryTab.classList.toggle('active', tab === 'summary'); sourceTab.classList.toggle('active', tab === 'source');
    summaryTab.setAttribute('aria-pressed', String(tab === 'summary')); sourceTab.setAttribute('aria-pressed', String(tab === 'source'));
    if (tab === 'source') renderSource(body, article); else renderSummary(body, article);
  }
  setArticleTab = setTab;
  const favorite = iconButton('star', article.favorite ? '取消收藏' : '收藏文章', event => busy(event.currentTarget, async () => {
    const updated = await api(`/articles/${id}`, { method: 'PATCH', body: { favorite: !article.favorite } });
    article.favorite = updated.favorite; favorite.classList.toggle('favorite-on', article.favorite); favorite.setAttribute('aria-label', article.favorite ? '取消收藏' : '收藏文章'); favorite.title = article.favorite ? '取消收藏' : '收藏文章';
    toast(article.favorite ? '已收藏文章' : '已取消收藏');
  }), article.favorite ? 'favorite-on' : '');
  const topicSelect = el('select', { 'aria-label': '将文章移动到主题', onchange: async event => {
    const previous = article.topic_id; event.target.disabled = true;
    try { await api(`/articles/${id}`, { method: 'PATCH', body: { topic_id: event.target.value || null } }); article.topic_id = event.target.value || null; tag.textContent = topicName(article.topic_id); await refreshTopics(); toast('主题已更新'); }
    catch (error) { event.target.value = previous || ''; toast(error.message, true); }
    finally { event.target.disabled = false; }
  } }, el('option', { value: '' }, '未归类'), state.topics.map(topic => el('option', { value: topic.id, selected: article.topic_id === topic.id }, topic.name)));
  const tag = el('span', { class: 'topic-tag' }, topicName(article.topic_id));
  const url = safeUrl(article.url);
  replace(main, 
    el('div', { class: 'detail-top' }, el('a', { class: 'back-link', href: article.topic_id ? `#/topic/${article.topic_id}` : '#/library' }, icon('back'), '返回文章列表'),
      el('div', { class: 'detail-controls' }, favorite, button(el('span', {}, '导出 Markdown'), () => exportArticle(article, messages), { symbol: 'download', kind: 'small', title: '导出原文、摘要和对话' }), iconButton('edit', '修改文章标题', () => titleDialog(article)), iconButton('trash', '删除文章', async () => {
        if (!await confirmDialog('删除这篇文章？', '原文、摘要、追问记录和包含这篇文章的主题对比会一并删除。需要保留时，请先导出备份。', '删除文章')) return;
        try { await api(`/articles/${id}`, { method: 'DELETE' }); toast('文章已删除'); navigate('/library'); } catch (error) { toast(error.message, true); }
      }))),
    el('div', { class: 'detail-grid' },
      el('article', { class: 'article-panel' }, el('div', { class: 'article-heading' }, tag, el('h1', {}, article.title), el('div', { class: 'article-info' }, el('time', { datetime: article.created_at }, date(article.created_at)), el('span', {}, countText(article)), el('span', {}, modeText(article.mode)), url && el('a', { href: url, target: '_blank', rel: 'noopener noreferrer' }, '查看来源 ↗'))),
        el('div', { class: 'detail-tabbar' }, el('div', { class: 'tabs' }, summaryTab, sourceTab), button('重新生成', event => busy(event.currentTarget, async () => {
          const updated = await api(`/articles/${id}/summarize`, { method: 'POST' });
          if (renderId !== state.renderId) return;
          Object.assign(article, updated); setTab('summary'); toast(updated.error ? `文章已保留，摘要失败：${updated.error}` : '摘要已重新生成', !!updated.error);
        }, '生成中…'), { kind: 'small', symbol: 'refresh' })), body,
        el('div', { class: 'article-actions' }, el('span', { class: 'muted', style: 'font-size:12px' }, '归属主题'), topicSelect)),
      chatPanel(article, messages, renderId)),
  );
  setTab('summary');
}
function safeUrl(value) { try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : null; } catch { return null; } }
function renderSummary(container, article) {
  const summary = article.summary;
  const section = (number, title, children) => el('section', { class: 'summary-section' }, el('h2', { class: 'summary-heading' }, el('span', { class: 'section-number' }, number), title), children);
  const list = items => el('ul', { class: 'summary-list' }, (items || []).map(text => citedText('li', text)));
  replace(container, article.error && notice(`文章已保存。摘要生成遇到问题：${article.error}。可点击「重新生成」重试。`, 'error'),
    article.mode !== 'ai' && notice('本地演示模式：以下内容通过原文摘句和规则整理，不具备语言模型的理解能力。可在服务器配置模型后重新生成。'),
    summary ? [section('01', '核心观点', list(summary.core_points)),
      section('02', '关键论据', (summary.arguments || []).map(argument => el('div', { class: 'argument' }, citedText('h4', argument.point), citedText('p', argument.evidence)))),
      section('03', '作者态度', el('div', { class: 'stance' }, citedText('p', summary.author_stance?.position), el('div', { class: 'stance-meta' }, el('span', { class: 'pill' }, `语气：${summary.author_stance?.tone || '未明确'}`), el('span', { class: 'pill' }, `判断把握：${summary.author_stance?.confidence || '未明确'}`)))),
      section('04', '可行动洞察', list(summary.insights)),
      summary.caveats?.length && section('05', '阅读提醒', list(summary.caveats))] : emptyState('摘要尚未生成', '你可以先阅读原文，或检查模型配置后点击「重新生成」。', button('连接设置', settingsDialog, { symbol: 'settings' })),
  );
}
function renderSource(container, article) {
  const paragraphs = article.text.split(/\n\s*\n/).filter(text => text.trim());
  replace(container, notice('段落编号用于核对摘要和追问的引用。模型的解读可能有偏差，请以原文为准。'), ...paragraphs.map((text, index) => el('section', { id: `p${index + 1}`, class: 'source-paragraph' }, el('span', { class: 'paragraph-id' }, `[p${index + 1}]`), text)));
}
function chatPanel(article, messages, renderId) {
  const body = el('div', { class: 'chat-body', 'aria-live': 'polite', 'aria-label': '追问记录' });
  const textarea = el('textarea', { 'aria-label': '输入追问', placeholder: '向这篇文章提一个问题…', maxlength: 2000, rows: 2 });
  const submit = el('button', { type: 'submit', 'aria-label': '发送追问', title: '发送追问' }, icon('send'));
  let sending = false;
  function drawMessages() {
    replace(body, messages.length ? messages.map(message => el('div', { class: `chat-msg ${message.role}` }, el('div', { class: 'chat-msg-label' }, message.role === 'user' ? '你' : `读懂 · ${modeText(message.mode)}`), citedText('div', message.content, 'chat-msg-body'))) : el('div', {}, el('div', { class: 'chat-welcome' }, icon('chat'), '从一个好问题开始', el('p', {}, '回答仅基于当前文章与对话。')),
      ['这个观点有什么漏洞？', '哪些论据最值得进一步验证？', '如何把这些观点应用到日常工作？'].map(question => el('button', { type: 'button', class: 'suggestion', onclick: () => { textarea.value = question; textarea.focus(); } }, question))));
    body.scrollTop = body.scrollHeight;
  }
  async function send(event) {
    event.preventDefault();
    const question = textarea.value.trim();
    if (!question || sending) { if (!question) textarea.focus(); return; }
    sending = true; submit.disabled = true; textarea.disabled = true;
    const thinking = el('div', { class: 'chat-msg' }, el('div', { class: 'chat-msg-label' }, el('span', { class: 'spinner' }), '正在阅读上下文…'));
    body.append(thinking); body.scrollTop = body.scrollHeight;
    try {
      const response = await api(`/articles/${article.id}/messages`, { method: 'POST', body: { question } });
      messages.push(response.user, response.assistant);
      if (renderId === state.renderId) { textarea.value = ''; drawMessages(); }
    } catch (error) { toast(error.message, true); }
    finally { sending = false; thinking.remove(); submit.disabled = false; textarea.disabled = false; if (renderId === state.renderId) textarea.focus(); }
  }
  textarea.addEventListener('keydown', event => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') send(event); });
  drawMessages();
  return el('aside', { class: 'chat-panel', 'aria-label': '文章追问' }, el('div', { class: 'chat-heading' }, el('h2', {}, icon('spark'), '与文章对话'), el('p', {}, state.config?.mode === 'ai' ? '带着问题阅读，让理解再深一点。' : '演示回答为规则模板，真实追问需配置模型。')), body,
    el('form', { class: 'chat-form', onsubmit: send }, el('div', { class: 'chat-input-wrap' }, textarea, submit), el('p', { class: 'chat-footnote' }, 'Ctrl / ⌘ + Enter 发送 · 请核对重要结论')));
}

function openDialog(title, content) {
  if (modal.open) modal.close();
  replace(modal, el('div', { class: 'modal-header' }, el('h2', { id: 'modal-title' }, title), iconButton('close', '关闭弹窗', () => modal.close())), content);
  modal.showModal();
}
function field(label, input, hint, optional = false) {
  const id = input.id || `field-${crypto.randomUUID()}`; input.id = id;
  return el('div', { class: 'field' }, el('label', { for: id }, label, optional && el('span', { class: 'optional' }, '选填')), input, hint && el('p', { class: 'field-hint' }, hint));
}
function formButtons(submitText, onCancel = () => modal.close()) { return el('div', { class: 'modal-actions' }, button('取消', onCancel), el('button', { type: 'submit', class: 'btn primary' }, submitText)); }
function topicOptions(selected) { return [el('option', { value: '' }, '暂不归类'), ...state.topics.map(topic => el('option', { value: topic.id, selected: selected === topic.id }, topic.name))]; }
function addArticleDialog(selectedTopic) {
  let mode = 'url'; let saving = false;
  const titleInput = el('input', { placeholder: '留空时自动提取标题', maxlength: 300 });
  const topicInput = el('select', {}, topicOptions(selectedTopic));
  const urlInput = el('input', { type: 'url', placeholder: 'https://example.com/article', inputmode: 'url', autocomplete: 'url' });
  const textInput = el('textarea', { minlength: 20, placeholder: '粘贴文章正文，建议保留段落空行…', maxlength: state.config?.max_text_length || 100000 });
  const inputArea = el('div');
  const error = el('div', { class: 'modal-error', role: 'alert' });
  const loading = el('div', { class: 'modal-loading hide', role: 'status' }, el('span', { class: 'spinner' }), '正在导入文章并生成摘要，请稍候…');
  const urlTab = el('button', { type: 'button', class: 'active', onclick: () => setMode('url') }, icon('link'), ' 文章链接');
  const textTab = el('button', { type: 'button', onclick: () => setMode('text') }, icon('text'), ' 粘贴正文');
  function setMode(value) {
    if (saving) return;
    mode = value; urlTab.classList.toggle('active', value === 'url'); textTab.classList.toggle('active', value === 'text');
    urlInput.required = value === 'url'; textInput.required = value === 'text';
    replace(inputArea, value === 'url' ? field('文章链接', urlInput, '支持公开可访问的 HTML 文章。登录、付费墙或提取失败时，请切换到粘贴正文。') : field('文章正文', textInput, `最多 ${(state.config?.max_text_length || 100000).toLocaleString()} 字。按空行区分段落，以便引用原文。`));
  }
  const form = el('form', { class: 'modal-body', onsubmit: async event => {
    event.preventDefault(); if (saving) return;
    saving = true; error.textContent = ''; loading.classList.remove('hide');
    const controls = [...form.querySelectorAll('button,input,textarea,select')]; controls.forEach(node => node.disabled = true);
    try {
      const body = { [mode]: (mode === 'url' ? urlInput.value : textInput.value).trim(), title: titleInput.value.trim() || undefined, topic_id: topicInput.value || undefined };
      const article = await api('/articles', { method: 'POST', body });
      modal.close(); toast(article.error ? '文章已保存，摘要可以稍后重试。' : '文章已导入，开始阅读吧。'); navigate(`/article/${article.id}`);
    } catch (problem) { error.textContent = problem.message; }
    finally { saving = false; loading.classList.add('hide'); controls.forEach(node => node.disabled = false); }
  } }, el('div', { class: 'modal-tabs' }, urlTab, textTab), inputArea, field('文章标题', titleInput, null, true), field('放入主题', topicInput, '也可以导入后，在文章详情中调整。', true), loading, error, formButtons('导入并生成摘要'));
  setMode('url'); openDialog('添加一篇文章', form);
}
function topicDialog(topic) {
  const name = el('input', { required: true, maxlength: 80, placeholder: '例如：人工智能与学习', value: topic?.name || '' });
  const description = el('textarea', { maxlength: 500, placeholder: '你想在这个主题下探索什么问题？', style: 'min-height:100px' }, topic?.description || '');
  const error = el('div', { class: 'modal-error', role: 'alert' });
  const form = el('form', { class: 'modal-body', onsubmit: async event => {
    event.preventDefault();
    const submit = $('button[type="submit"]', form); submit.disabled = true; error.textContent = '';
    try {
      const result = await api(topic ? `/topics/${topic.id}` : '/topics', { method: topic ? 'PATCH' : 'POST', body: { name: name.value.trim(), description: description.value.trim() } });
      modal.close(); toast(topic ? '主题已更新' : '主题已创建'); navigate(`/topic/${result.id}`);
    } catch (problem) { error.textContent = problem.message; }
    finally { submit.disabled = false; }
  } }, field('主题名称', name), field('主题说明', description, null, true), error, formButtons(topic ? '保存更改' : '创建主题'));
  openDialog(topic ? '编辑主题' : '创建一个主题', form);
}
function titleDialog(article) {
  const input = el('input', { required: true, maxlength: 300, value: article.title });
  const error = el('div', { class: 'modal-error', role: 'alert' });
  const form = el('form', { class: 'modal-body', onsubmit: async event => {
    event.preventDefault(); const submit = $('button[type="submit"]', form); submit.disabled = true;
    try { await api(`/articles/${article.id}`, { method: 'PATCH', body: { title: input.value.trim() } }); modal.close(); toast('标题已更新'); renderRoute(); }
    catch (problem) { error.textContent = problem.message; } finally { submit.disabled = false; }
  } }, field('文章标题', input), error, formButtons('保存标题'));
  openDialog('修改文章标题', form);
}
function confirmDialog(title, message, confirmLabel) {
  return new Promise(resolve => {
    const confirm = button(confirmLabel, () => { modal.close('confirmed'); }, { kind: 'danger' });
    openDialog(title, el('div', { class: 'modal-body' }, el('p', { class: 'subtitle', style: 'margin:0 0 25px' }, message), el('div', { class: 'modal-actions' }, button('取消', () => modal.close()), confirm)));
    modal.addEventListener('close', () => resolve(modal.returnValue === 'confirmed'), { once: true });
    modal.returnValue = '';
  });
}
function settingsDialog() {
  const input = el('input', { type: 'password', autocomplete: 'off', value: token, placeholder: '未设置 APP_ACCESS_TOKEN 时留空' });
  const error = el('div', { class: 'modal-error', role: 'alert' });
  const form = el('form', { class: 'modal-body', onsubmit: async event => {
    event.preventDefault(); token = input.value.trim();
    try { if (token) localStorage.setItem('reading-access-token', token); else localStorage.removeItem('reading-access-token'); } catch { /* Session use still works. */ }
    const submit = $('button[type="submit"]', form); submit.disabled = true; error.textContent = '';
    try { await refreshConfig(); modal.close(); toast('连接设置已保存'); renderRoute(); }
    catch (problem) { error.textContent = problem.message; } finally { submit.disabled = false; }
  } }, el('div', { class: 'settings-block' }, el('strong', {}, `当前状态：${state.config ? state.config.mode === 'ai' ? '真实 AI 模式' : '本地演示模式' : '未连接'}`), el('p', {}, state.config?.mode === 'ai' ? `模型：${state.config.model}` : '演示模式可体验完整流程，摘要与回答由本地规则生成。'), el('p', {}, '真实模型密钥在服务器 .env 中配置：AI_MODE、AI_API_KEY、AI_BASE_URL、AI_MODEL。')),
    field('应用访问令牌', input, '这是服务器的 APP_ACCESS_TOKEN，用于保护应用访问。不是模型 API 密钥。', true), el('p', { class: 'settings-note' }, '访问令牌保存在当前浏览器的本地存储中。模型 API 密钥只应保留在服务器，不要粘贴到文章或聊天中。'), error, formButtons('保存并连接'));
  openDialog('模型与连接设置', form);
}

function download(filename, text, type) {
  const blob = new Blob([text], { type }); const url = URL.createObjectURL(blob);
  const link = el('a', { href: url, download: filename }); document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 20000);
}
async function exportBackup() {
  try { const data = await api('/export'); download(`reading-backup-${new Date().toISOString().slice(0, 10)}.json`, JSON.stringify(data, null, 2), 'application/json;charset=utf-8'); toast('数据备份已导出，包含文章、主题、摘要和对话。'); }
  catch (error) { toast(error.message, true); }
}
function exportArticle(article, messages) {
  const summary = article.summary;
  const lines = [`# ${article.title}`, '', `- 添加时间：${date(article.created_at)}`, `- 模式：${modeText(article.mode)}`, `- 主题：${topicName(article.topic_id)}`, article.url ? `- 原文：${article.url}` : '', ''];
  if (summary) {
    for (const [title, items] of [['核心观点', summary.core_points], ['可行动洞察', summary.insights], ['阅读提醒', summary.caveats]]) { lines.push(`## ${title}`, '', ...(items || []).map(item => `- ${item}`), ''); }
    lines.push('## 关键论据', '', ...(summary.arguments || []).flatMap(item => [`### ${item.point}`, '', item.evidence, '']), '## 作者态度', '', summary.author_stance?.position || '', `语气：${summary.author_stance?.tone || ''}；判断把握：${summary.author_stance?.confidence || ''}`, '');
  }
  lines.push('## 原文', '', ...article.text.split(/\n\s*\n/).filter(text => text.trim()).flatMap((text, index) => [`[p${index + 1}]`, text, '']));
  if (messages.length) lines.push('## 追问记录', '', ...messages.flatMap(item => [`### ${item.role === 'user' ? '你' : `读懂 · ${modeText(item.mode)}`}`, '', item.content, '']));
  download(`${article.title.replace(/[<>:"/\\|?*\x00-\x1F]/g, '_').slice(0, 70) || 'article'}.md`, lines.join('\n'), 'text/markdown;charset=utf-8');
  toast('Markdown 已导出');
}
async function importBackup(file) {
  if (!file) return;
  if (file.size > 20 * 1024 * 1024) { toast('备份文件不能超过 20 MB。', true); return; }
  try {
    const data = JSON.parse(await file.text());
    if (data.version !== 1 || !Array.isArray(data.articles) || !Array.isArray(data.topics)) throw new Error('备份格式无效，请选择本应用导出的 JSON 文件。');
    if (!await confirmDialog('导入数据备份？', `准备导入 ${data.articles.length} 篇文章、${data.topics.length} 个主题。导入会合并到当前数据，相同标识的记录会跳过；主题重名或引用无效时整批导入会取消。建议先导出现有备份。`, '确认导入')) return;
    await api('/import', { method: 'POST', body: data }); toast('备份已导入'); renderRoute();
  } catch (error) { toast(error.message, true); }
}
const EXAMPLE_TEXT = `学习的效率，不只取决于投入时间\n\n许多人把学习等同于长时间阅读和反复划线。但读过，并不意味着能够在需要时使用。学习的目标应该是形成可以解释、检验和迁移的理解，而不是累计看完的页数。\n\n主动回忆是一种值得尝试的方法。读完一个小节后，暂时合上材料，用自己的话复述核心观点，再回到原文核对。无法解释清楚的地方，往往暴露了理解的空缺。这比一直盯着熟悉的文字更能帮助发现问题。\n\n另一种方法是把新知识与已有经验建立联系。例如读到“反馈循环”，可以联想到团队复盘：目标、行动、观察结果与调整方案之间形成循环。建立联系能帮助理解，但类比也有边界，不能因为两个概念相似，就认为它们在所有情境中都相同。\n\n不过，任何学习方法都受到背景知识、任务难度和个人状态的影响。单靠自我感觉来判断效率，容易高估熟悉感。一个更可靠的做法是在一周后做一次小测，记录是否能够独立解决问题，而不仅是记得曾经读过。\n\n我的建议是做一个小实验：未来一周，每天阅读后花五分钟写下三个观点和一个疑问；周末用一道真实问题检验自己的理解。如果结果没有改善，再调整方法。学习策略应当服务于实际目标，而不是成为额外的负担。`;
const EXAMPLE_COUNTERPOINT = `别急着把所有阅读都变成测试\n\n学习确实需要检验，但并非所有阅读都以解决眼前问题为目的。有些文章的价值在于打开视野、提供审美经验，或让一个尚未成形的问题慢慢浮现。如果每一次阅读都立即安排测验，可能会让读者只关注容易量化的结果。\n\n深度阅读有时需要连续投入较长时间。频繁打断阅读并要求复述，虽然可能强化某些知识，却也可能破坏理解复杂论证所需要的连贯感。面对一篇历史叙事或哲学论述，先完整读完再梳理结构，或许更适合初学者。\n\n这不意味着主动回忆没有价值。对于准备考试、训练操作技能或学习明确概念，它可以成为很有用的工具。但工具的适用范围应当由目标决定，不能把一个在特定任务上有效的方法，当成所有学习问题的唯一答案。\n\n关于学习效果的判断，也应该纳入更长期的观察。一次小测可能反映短期记忆，却未必能反映创造性联想、独立判断或对问题的兴趣。因此，评价阅读的收获时，应同时考虑能够复述什么、提出了什么新问题，以及未来是否愿意继续探索。\n\n我建议把阅读分成两种节奏：带着具体目标时，使用回忆、练习与反馈；自由探索时，允许慢读、停留和暂时不懂。每周回看笔记，寻找不同材料之间的联系。好的学习计划应当保留一些没有立即产出的空间。`;
async function createExample(buttonNode) {
  await busy(buttonNode, async () => {
    const suffix = new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date());
    const topic = await api('/topics', { method: 'POST', body: { name: `学习方法 · 示例 ${suffix}`, description: '两篇立场不同的自编示例：主动回忆与自由阅读。选择它们，体验主题对比。' } });
    await api('/articles', { method: 'POST', body: { title: '示例 A：学习的效率，不只取决于投入时间', text: EXAMPLE_TEXT, topic_id: topic.id } });
    await api('/articles', { method: 'POST', body: { title: '示例 B：别急着把所有阅读都变成测试', text: EXAMPLE_COUNTERPOINT, topic_id: topic.id } });
    toast('两篇示例已加入主题，勾选文章即可对比。'); navigate(`/topic/${topic.id}`);
  }, '正在导入示例…');
}

$('#menu-toggle').addEventListener('click', () => { const open = $('#sidebar').classList.toggle('open'); $('#menu-toggle').setAttribute('aria-expanded', String(open)); });
document.addEventListener('click', event => { if (!event.target.closest('.sidebar') && !event.target.closest('#menu-toggle')) closeMenu(); });
$('#mode-button').addEventListener('click', settingsDialog);
$('#import-file').addEventListener('change', event => { importBackup(event.target.files[0]); event.target.value = ''; });
window.addEventListener('hashchange', () => { window.scrollTo({ top: 0 }); renderRoute(); });
modal.addEventListener('click', event => { if (event.target === modal) { const rect = modal.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) modal.close(); } });
sidebar();
refreshConfig().catch(error => { $('#mode-label').textContent = '连接需要检查'; toast(error.message, true); });
renderRoute();





