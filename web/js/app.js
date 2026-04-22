/**
 * 主页逻辑
 *
 * - 根据当前登录用户是否为 admin 决定左侧 tab 与主内容
 *   · 普通用户：反馈（会话列表 + 详情对话）
 *   · admin   ：反馈处理（全部用户反馈 + 详情对话 + 状态管理）
 */

(function () {
    if (!getToken()) { location.href = 'index.html'; return; }

    const $ = id => document.getElementById(id);

    const STATUS_LABEL = {
        open: '待处理',
        processing: '处理中',
        resolved: '已解决',
        closed: '已关闭',
    };

    const state = {
        user: getCurrentUser() || { name: '-', user_id: '-' },
        isAdmin: false,
        currentTab: '',

        // 普通用户反馈
        feedbackPage: 1,
        feedbackPageSize: 10,
        feedbackTotal: 0,
        activeFeedbackKey: null,

        // 管理员反馈
        adminPage: 1,
        adminPageSize: 10,
        adminTotal: 0,
        adminStatus: '',
        activeAdminFeedback: null,  // { user_id, feedback_key }
    };

    // ========== 通用工具 ==========

    function setViewActive(tab) {
        state.currentTab = tab;
        document.querySelectorAll('.view').forEach(el => {
            el.classList.toggle('active', el.id === `view-${tab}`);
        });
        document.querySelectorAll('.tab-item[data-tab]').forEach(el => {
            el.classList.toggle('active', el.dataset.tab === tab);
        });
    }

    function showSubview(sectionId, subviewId) {
        const section = document.getElementById(sectionId);
        if (!section) return;
        section.querySelectorAll('.subview').forEach(sub => {
            sub.hidden = sub.id !== subviewId;
        });
    }

    function switchTab(tab) {
        setViewActive(tab);
        if (tab === 'feedback') {
            showSubview('view-feedback', 'feedback-list-view');
            loadFeedbacks();
        } else if (tab === 'admin-feedback') {
            showSubview('view-admin-feedback', 'admin-feedback-list-view');
            loadAdminFeedbacks();
        } else if (tab === 'user') {
            renderProfile();
        }
    }

    function renderProfile() {
        $('profileName').textContent = state.user.name || '-';
        $('profileUserId').textContent = state.user.user_id || '-';
    }

    function renderPager(containerId, total, pageSize, currentPage, onChange) {
        const pagerEl = $(containerId);
        const totalPages = Math.max(1, Math.ceil(total / pageSize));
        if (total === 0) { pagerEl.innerHTML = ''; return; }

        let html = '';
        html += `<button ${currentPage <= 1 ? 'disabled' : ''} data-page="${currentPage - 1}">上一页</button>`;
        for (let i = 1; i <= totalPages; i++) {
            if (i === currentPage) {
                html += `<button class="current" disabled>${i}</button>`;
            } else if (
                i === 1 || i === totalPages ||
                (i >= currentPage - 2 && i <= currentPage + 2)
            ) {
                html += `<button data-page="${i}">${i}</button>`;
            } else if (i === currentPage - 3 || i === currentPage + 3) {
                html += `<span style="color:#97a3b4;padding:0 4px;">…</span>`;
            }
        }
        html += `<button ${currentPage >= totalPages ? 'disabled' : ''} data-page="${currentPage + 1}">下一页</button>`;
        pagerEl.innerHTML = html;
        pagerEl.querySelectorAll('button[data-page]').forEach(btn => {
            btn.addEventListener('click', () => {
                const next = parseInt(btn.dataset.page, 10);
                if (next >= 1 && next !== currentPage) onChange(next);
            });
        });
    }

    function statusChipHTML(status) {
        const cls = `status-chip status-${status || 'open'}`;
        return `<span class="${cls}">${escapeHTML(STATUS_LABEL[status] || status || '-')}</span>`;
    }

    function applyStatusChip(elId, status) {
        const el = document.getElementById(elId);
        if (!el) return;
        el.className = `status-chip status-${status || 'open'}`;
        el.textContent = STATUS_LABEL[status] || status || '-';
    }

    function renderThread(containerId, messages) {
        const el = $(containerId);
        if (!messages || messages.length === 0) {
            el.innerHTML = '<div class="empty-placeholder">暂无消息</div>';
            return;
        }
        el.innerHTML = messages.map(m => {
            const mineCls = m.sender_type === 'user' ? 'mine' : 'peer';
            const label = m.sender_type === 'admin'
                ? (m.sender_name ? `管理员 · ${escapeHTML(m.sender_name)}` : '管理员')
                : (m.sender_name ? escapeHTML(m.sender_name) : '用户');
            return `
                <div class="chat-message ${mineCls}">
                    <div class="chat-meta">
                        <span class="chat-sender">${label}</span>
                        <span class="chat-time">${escapeHTML(formatTime(m.created_at))}</span>
                    </div>
                    <div class="chat-bubble">${escapeHTML(m.content)}</div>
                </div>
            `;
        }).join('');
        el.scrollTop = el.scrollHeight;
    }

    // ========== 普通用户：反馈列表 ==========

    async function loadFeedbacks() {
        const listEl = $('feedbackList');
        listEl.innerHTML = '<div class="empty-placeholder">加载中...</div>';
        $('feedbackPager').innerHTML = '';
        try {
            const resp = await feedbackAPI.list(state.feedbackPage, state.feedbackPageSize);
            const { items, total } = resp.data;
            state.feedbackTotal = total || 0;
            if (!items || items.length === 0) {
                listEl.innerHTML = '<div class="empty-placeholder">当前暂无反馈</div>';
            } else {
                listEl.innerHTML = items.map(renderUserFeedbackCard).join('');
                listEl.querySelectorAll('.feedback-item').forEach(el => {
                    el.addEventListener('click', () => openFeedbackDetail(el.dataset.key));
                });
            }
            renderPager('feedbackPager', state.feedbackTotal, state.feedbackPageSize,
                        state.feedbackPage, p => { state.feedbackPage = p; loadFeedbacks(); });
        } catch (e) {
            listEl.innerHTML = `<div class="empty-placeholder">加载失败：${escapeHTML(e.message)}</div>`;
        }
    }

    function renderUserFeedbackCard(item) {
        const preview = item.last_message || item.title || '(无内容)';
        return `
            <div class="feedback-item clickable" data-key="${escapeHTML(item.feedback_key)}">
                <div class="feedback-item-head">
                    <span class="feedback-key">#${escapeHTML(item.feedback_key)}</span>
                    ${statusChipHTML(item.status)}
                    <span class="feedback-time">${escapeHTML(formatTime(item.last_message_at || item.updated_at))}</span>
                </div>
                <div class="feedback-title">${escapeHTML(item.title || '未命名反馈')}</div>
                <div class="feedback-preview">${escapeHTML(preview)}</div>
            </div>
        `;
    }

    async function openFeedbackDetail(key) {
        state.activeFeedbackKey = key;
        showSubview('view-feedback', 'feedback-detail-view');
        $('feedbackThread').innerHTML = '<div class="empty-placeholder">加载中...</div>';
        $('feedbackReplyInput').value = '';
        $('feedbackReplyHint').textContent = '';
        try {
            const resp = await feedbackAPI.detail(key);
            const { feedback, messages } = resp.data;
            $('feedbackDetailTitle').textContent = feedback.title || '反馈详情';
            applyStatusChip('feedbackDetailStatus', feedback.status);
            renderThread('feedbackThread', messages);
        } catch (e) {
            $('feedbackThread').innerHTML = `<div class="empty-placeholder">加载失败：${escapeHTML(e.message)}</div>`;
        }
    }

    async function sendUserReply(ev) {
        ev.preventDefault();
        const hintEl = $('feedbackReplyHint');
        hintEl.textContent = '';
        const content = $('feedbackReplyInput').value.trim();
        if (!content) { hintEl.textContent = '请输入内容'; return; }
        const btn = $('feedbackReplyBtn');
        btn.disabled = true;
        try {
            await feedbackAPI.sendMessage(state.activeFeedbackKey, content);
            $('feedbackReplyInput').value = '';
            await openFeedbackDetail(state.activeFeedbackKey);
        } catch (e) {
            hintEl.textContent = e.message || '发送失败';
        } finally {
            btn.disabled = false;
        }
    }

    // ========== 新增反馈弹窗 ==========

    function openFeedbackModal() {
        $('feedbackContent').value = '';
        $('feedbackHint').textContent = '';
        $('feedbackModal').hidden = false;
        setTimeout(() => $('feedbackContent').focus(), 40);
    }
    function closeFeedbackModal() { $('feedbackModal').hidden = true; }

    async function submitNewFeedback() {
        const content = $('feedbackContent').value.trim();
        const hintEl = $('feedbackHint');
        if (!content) { hintEl.textContent = '请输入反馈内容'; return; }
        const btn = $('feedbackSubmitBtn');
        btn.disabled = true;
        try {
            await feedbackAPI.create(content);
            closeFeedbackModal();
            state.feedbackPage = 1;
            loadFeedbacks();
        } catch (e) {
            hintEl.textContent = e.message || '提交失败';
        } finally {
            btn.disabled = false;
        }
    }

    // ========== 管理员：反馈处理列表 ==========

    async function loadAdminFeedbacks() {
        const listEl = $('adminFeedbackList');
        listEl.innerHTML = '<div class="empty-placeholder">加载中...</div>';
        $('adminFeedbackPager').innerHTML = '';
        try {
            const resp = await adminAPI.listFeedback(
                state.adminPage, state.adminPageSize, state.adminStatus
            );
            const { items, total } = resp.data;
            state.adminTotal = total || 0;
            if (!items || items.length === 0) {
                listEl.innerHTML = '<div class="empty-placeholder">暂无反馈</div>';
            } else {
                listEl.innerHTML = items.map(renderAdminFeedbackCard).join('');
                listEl.querySelectorAll('.feedback-item').forEach(el => {
                    el.addEventListener('click', () => openAdminFeedbackDetail(
                        parseInt(el.dataset.userId, 10), el.dataset.key
                    ));
                });
            }
            renderPager('adminFeedbackPager', state.adminTotal, state.adminPageSize,
                        state.adminPage, p => { state.adminPage = p; loadAdminFeedbacks(); });
        } catch (e) {
            listEl.innerHTML = `<div class="empty-placeholder">加载失败：${escapeHTML(e.message)}</div>`;
        }
    }

    function renderAdminFeedbackCard(item) {
        const preview = item.last_message || item.title || '(无内容)';
        const who = item.user_name
            ? `${escapeHTML(item.user_name)} (#${item.user_id})`
            : `#${item.user_id}`;
        return `
            <div class="feedback-item clickable"
                 data-user-id="${item.user_id}"
                 data-key="${escapeHTML(item.feedback_key)}">
                <div class="feedback-item-head">
                    <span class="feedback-key">#${escapeHTML(item.feedback_key)}</span>
                    ${statusChipHTML(item.status)}
                    <span class="feedback-user">${who}</span>
                    <span class="feedback-time">${escapeHTML(formatTime(item.last_message_at || item.updated_at))}</span>
                </div>
                <div class="feedback-title">${escapeHTML(item.title || '未命名反馈')}</div>
                <div class="feedback-preview">${escapeHTML(preview)}</div>
            </div>
        `;
    }

    async function openAdminFeedbackDetail(userId, key) {
        state.activeAdminFeedback = { user_id: userId, feedback_key: key };
        showSubview('view-admin-feedback', 'admin-feedback-detail-view');
        $('adminFeedbackThread').innerHTML = '<div class="empty-placeholder">加载中...</div>';
        $('adminReplyInput').value = '';
        $('adminReplyHint').textContent = '';
        $('adminDetailMeta').innerHTML = '';
        try {
            const resp = await adminAPI.feedbackDetail(userId, key);
            const { feedback, user, messages } = resp.data;
            $('adminFeedbackDetailTitle').textContent = feedback.title || '反馈详情';
            applyStatusChip('adminFeedbackDetailStatus', feedback.status);
            $('adminStatusSelect').value = feedback.status || 'open';
            $('adminDetailMeta').innerHTML = `
                <span>提交者：<b>${escapeHTML(user.name || '-')}</b> (#${user.user_id})</span>
                <span>反馈编号：<code>${escapeHTML(feedback.feedback_key)}</code></span>
                <span>创建时间：${escapeHTML(formatTime(feedback.created_at))}</span>
            `;
            renderThread('adminFeedbackThread', messages);
        } catch (e) {
            $('adminFeedbackThread').innerHTML =
                `<div class="empty-placeholder">加载失败：${escapeHTML(e.message)}</div>`;
        }
    }

    async function sendAdminReply(ev) {
        ev.preventDefault();
        const hintEl = $('adminReplyHint');
        hintEl.textContent = '';
        const content = $('adminReplyInput').value.trim();
        if (!content) { hintEl.textContent = '请输入回复内容'; return; }
        if (!state.activeAdminFeedback) return;
        const btn = $('adminReplyBtn');
        btn.disabled = true;
        try {
            const { user_id, feedback_key } = state.activeAdminFeedback;
            await adminAPI.reply(user_id, feedback_key, content);
            $('adminReplyInput').value = '';
            await openAdminFeedbackDetail(user_id, feedback_key);
        } catch (e) {
            hintEl.textContent = e.message || '发送失败';
        } finally {
            btn.disabled = false;
        }
    }

    async function onAdminStatusChange(ev) {
        const newStatus = ev.target.value;
        if (!state.activeAdminFeedback) return;
        const { user_id, feedback_key } = state.activeAdminFeedback;
        try {
            await adminAPI.changeStatus(user_id, feedback_key, newStatus);
            await openAdminFeedbackDetail(user_id, feedback_key);
        } catch (e) {
            alert('状态更新失败：' + (e.message || '未知错误'));
        }
    }

    // ========== 初始化 / 角色路由 ==========

    function applyRoleUI() {
        const isAdmin = (state.user.name || '').toLowerCase() === 'admin';
        state.isAdmin = isAdmin;
        document.querySelectorAll('.tab-role-user').forEach(el => { el.hidden = isAdmin; });
        document.querySelectorAll('.tab-role-admin').forEach(el => { el.hidden = !isAdmin; });
        $('userTabName').textContent = state.user.name || '用户';
    }

    async function syncCurrentUser() {
        try {
            const resp = await userAPI.me();
            if (resp && resp.data) {
                state.user = resp.data;
                saveAuth({ ...state.user, token: getToken() });
                applyRoleUI();
                renderProfile();
            }
        } catch (_) { /* 401 已跳登录页 */ }
    }

    async function applyBranding() {
        await initAPIConfig();
        // 根据下发的 RUM 配置按需初始化 Aegis；未启用或缺失时为 no-op。
        if (typeof initRUM === 'function') {
            initRUM(window.__RUM_CONFIG__);
        }
        const name = getAppName();
        $('brandName').textContent = name;
        document.title = name;
    }

    function bind() {
        document.querySelectorAll('.tab-item[data-tab]').forEach(el => {
            el.addEventListener('click', () => switchTab(el.dataset.tab));
        });
        $('logoutBtn').addEventListener('click', async () => {
            try { await userAPI.logout(); } catch (_) { /* ignore */ }
            clearAuth();
            location.href = 'index.html';
        });

        // 普通用户 - 新增反馈
        $('newFeedbackBtn').addEventListener('click', openFeedbackModal);
        $('feedbackModalClose').addEventListener('click', closeFeedbackModal);
        $('feedbackCancelBtn').addEventListener('click', closeFeedbackModal);
        $('feedbackSubmitBtn').addEventListener('click', submitNewFeedback);
        $('feedbackModal').addEventListener('click', ev => {
            if (ev.target.id === 'feedbackModal') closeFeedbackModal();
        });

        // 普通用户 - 会话
        $('feedbackBackBtn').addEventListener('click', () => {
            showSubview('view-feedback', 'feedback-list-view');
        });
        $('feedbackComposer').addEventListener('submit', sendUserReply);

        // 管理员 - 会话
        $('adminFeedbackBackBtn').addEventListener('click', () => {
            showSubview('view-admin-feedback', 'admin-feedback-list-view');
        });
        $('adminFeedbackComposer').addEventListener('submit', sendAdminReply);
        $('adminStatusSelect').addEventListener('change', onAdminStatusChange);
        $('adminStatusFilter').addEventListener('change', ev => {
            state.adminStatus = ev.target.value;
            state.adminPage = 1;
            loadAdminFeedbacks();
        });
    }

    (async function init() {
        await applyBranding();
        applyRoleUI();
        bind();
        switchTab(state.isAdmin ? 'admin-feedback' : 'feedback');
        syncCurrentUser();  // 后台同步，确认角色
    })();
})();
