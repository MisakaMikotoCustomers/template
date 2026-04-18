/**
 * 通用工具：本地存储 / 简单 UUID / 密码哈希
 */

const TOKEN_KEY = 'tpl_token';
const USER_KEY = 'tpl_user';

function saveAuth(userInfo) {
    localStorage.setItem(TOKEN_KEY, userInfo.token || '');
    localStorage.setItem(USER_KEY, JSON.stringify({
        user_id: userInfo.user_id,
        name: userInfo.name,
    }));
}

function getToken() {
    return localStorage.getItem(TOKEN_KEY) || '';
}

function getCurrentUser() {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try { return JSON.parse(raw); } catch (e) { return null; }
}

function clearAuth() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
}

function generateUUID() {
    if (window.crypto && window.crypto.randomUUID) {
        return window.crypto.randomUUID();
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
        const r = (Math.random() * 16) | 0;
        const v = c === 'x' ? r : (r & 0x3) | 0x8;
        return v.toString(16);
    });
}

/** 浏览器端做一次 SHA-256，避免明文密码跨网络传输 */
async function hashPassword(plain) {
    const enc = new TextEncoder().encode(plain);
    const buf = await crypto.subtle.digest('SHA-256', enc);
    return Array.from(new Uint8Array(buf))
        .map(b => b.toString(16).padStart(2, '0'))
        .join('');
}

function escapeHTML(str) {
    if (str == null) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function formatTime(iso) {
    if (!iso) return '-';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
           `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/**
 * 全局调试浮层：展示后端返回的原始异常信息（type/message/traceback）。
 *
 * 使用场景：后端 500/400 异常响应的 data.debug 字段，由 api.js 在抛错时
 * 自动调用，这样无需改动每个业务页面的 try/catch 就能看到完整堆栈。
 *
 * 面板设计为右下角非阻塞卡片，可最小化、可折叠 traceback、可一键复制，
 * 不影响现有内联错误提示（e.message 仍会在各 hint 位置显示）。
 */
const DEBUG_OVERLAY_ID = '__tpl_debug_overlay__';

function _ensureDebugOverlay() {
    let root = document.getElementById(DEBUG_OVERLAY_ID);
    if (root) return root;
    root = document.createElement('div');
    root.id = DEBUG_OVERLAY_ID;
    root.style.cssText = [
        'position:fixed', 'right:16px', 'bottom:16px', 'z-index:99999',
        'display:flex', 'flex-direction:column', 'gap:10px',
        'max-width:min(560px, calc(100vw - 32px))',
        'max-height:calc(100vh - 32px)', 'overflow:hidden',
        'pointer-events:none',
    ].join(';');
    document.body.appendChild(root);
    return root;
}

function showDebugPanel({ title, message, debug, traceId }) {
    const root = _ensureDebugOverlay();
    const card = document.createElement('div');
    card.style.cssText = [
        'pointer-events:auto',
        'background:#1f2430', 'color:#f0f3f8',
        'border:1px solid #ff6b6b', 'border-radius:10px',
        'box-shadow:0 8px 28px rgba(0,0,0,.35)',
        'font:12px/1.55 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
        'display:flex', 'flex-direction:column', 'overflow:hidden',
    ].join(';');

    const head = document.createElement('div');
    head.style.cssText = [
        'display:flex', 'align-items:center', 'gap:8px',
        'padding:8px 12px', 'background:#2a3140',
        'border-bottom:1px solid #3a4355',
    ].join(';');
    const badge = document.createElement('span');
    badge.textContent = (debug && debug.type ? debug.type.split('.').pop() : 'Error');
    badge.style.cssText = 'background:#ff6b6b;color:#fff;padding:1px 6px;border-radius:4px;font-weight:600;';
    head.appendChild(badge);
    const titleEl = document.createElement('span');
    titleEl.textContent = title || '后端异常';
    titleEl.style.cssText = 'font-weight:600;flex:0 0 auto;';
    head.appendChild(titleEl);
    const spacer = document.createElement('span');
    spacer.style.cssText = 'flex:1 1 auto;';
    head.appendChild(spacer);

    function mkBtn(label, onClick) {
        const b = document.createElement('button');
        b.type = 'button';
        b.textContent = label;
        b.style.cssText = [
            'background:transparent', 'color:#cfd6e2',
            'border:1px solid #4a5468', 'border-radius:4px',
            'padding:2px 8px', 'cursor:pointer', 'font-size:12px',
        ].join(';');
        b.addEventListener('click', onClick);
        return b;
    }
    const body = document.createElement('div');
    body.style.cssText = 'padding:10px 12px;overflow:auto;max-height:50vh;';
    const toggleBtn = mkBtn('折叠', () => {
        const hidden = body.style.display === 'none';
        body.style.display = hidden ? 'block' : 'none';
        toggleBtn.textContent = hidden ? '折叠' : '展开';
    });
    const copyBtn = mkBtn('复制', async () => {
        const text = [
            title || '',
            message || '',
            traceId ? `traceId: ${traceId}` : '',
            debug ? `type: ${debug.type}` : '',
            debug ? `message: ${debug.message}` : '',
            debug && debug.cause ? `cause: ${debug.cause}` : '',
            debug && debug.traceback ? `\n${debug.traceback}` : '',
        ].filter(Boolean).join('\n');
        try { await navigator.clipboard.writeText(text); copyBtn.textContent = '已复制'; }
        catch (_) { copyBtn.textContent = '复制失败'; }
        setTimeout(() => { copyBtn.textContent = '复制'; }, 1500);
    });
    const closeBtn = mkBtn('×', () => card.remove());
    closeBtn.style.padding = '2px 10px';
    head.appendChild(toggleBtn);
    head.appendChild(copyBtn);
    head.appendChild(closeBtn);
    card.appendChild(head);

    function line(label, value, mono = false) {
        if (!value) return;
        const row = document.createElement('div');
        row.style.cssText = 'margin-bottom:6px;word-break:break-word;';
        const k = document.createElement('span');
        k.textContent = `${label}: `;
        k.style.cssText = 'color:#97a3b4;';
        const v = document.createElement('span');
        v.textContent = value;
        if (mono) v.style.cssText = 'white-space:pre;display:block;margin-top:4px;color:#ffd166;';
        row.appendChild(k);
        row.appendChild(v);
        body.appendChild(row);
    }
    line('message', message);
    if (debug) {
        line('type', debug.type);
        if (debug.message && debug.message !== message) line('detail', debug.message);
        if (debug.cause) line('cause', debug.cause);
        if (debug.traceback) line('traceback', debug.traceback, true);
    }
    if (traceId) line('traceId', traceId);
    card.appendChild(body);

    root.appendChild(card);
    return card;
}
