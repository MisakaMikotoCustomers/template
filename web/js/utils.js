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

/**
 * 浏览器端做一次 SHA-256，避免明文密码跨网络传输
 *
 * 兼容说明：WebCrypto 的 `crypto.subtle` 仅在 Secure Context 下暴露
 * （HTTPS 或 http://localhost）。ai-task 测试环境下发的 HTTP 域名不是
 * Secure Context，`crypto.subtle` 为 undefined，直接调用会抛
 * "Cannot read properties of undefined (reading 'digest')"。此处加纯 JS
 * 兜底实现，输出与原生 WebCrypto 完全一致的 64 位小写 hex，保证后端
 * 无论用户从 HTTP 还是 HTTPS 注册，hash 都能对上。
 */
async function hashPassword(plain) {
    const text = plain || '';
    if (typeof window !== 'undefined'
        && window.isSecureContext
        && window.crypto && window.crypto.subtle) {
        const enc = new TextEncoder().encode(text);
        const buf = await window.crypto.subtle.digest('SHA-256', enc);
        return Array.from(new Uint8Array(buf))
            .map(b => b.toString(16).padStart(2, '0'))
            .join('');
    }
    return _sha256HexFallback(text);
}

/** 纯 JS SHA-256（UTF-8 字节 -> 64 位小写 hex）。仅在 WebCrypto 不可用时走。 */
function _sha256HexFallback(str) {
    const bytes = _utf8Encode(str);
    const bitLen = bytes.length * 8;
    const rem = bytes.length % 64;
    const padLen = rem < 56 ? 56 - rem : 120 - rem;
    const total = bytes.length + padLen + 8;
    const buf = new Uint8Array(total);
    buf.set(bytes);
    buf[bytes.length] = 0x80;
    const dv = new DataView(buf.buffer);
    dv.setUint32(total - 8, Math.floor(bitLen / 0x100000000), false);
    dv.setUint32(total - 4, bitLen >>> 0, false);

    const K = [
        0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
        0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
        0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
        0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
        0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
        0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
        0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
        0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2,
    ];
    const H = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
    const W = new Uint32Array(64);
    const rotr = (x, n) => (x >>> n) | (x << (32 - n));

    for (let chunk = 0; chunk < total; chunk += 64) {
        for (let i = 0; i < 16; i++) W[i] = dv.getUint32(chunk + i * 4, false);
        for (let i = 16; i < 64; i++) {
            const w15 = W[i - 15], w2 = W[i - 2];
            const s0 = rotr(w15, 7) ^ rotr(w15, 18) ^ (w15 >>> 3);
            const s1 = rotr(w2, 17) ^ rotr(w2, 19) ^ (w2 >>> 10);
            W[i] = (W[i - 16] + s0 + W[i - 7] + s1) >>> 0;
        }
        let a = H[0], b = H[1], c = H[2], d = H[3], e = H[4], f = H[5], g = H[6], h = H[7];
        for (let i = 0; i < 64; i++) {
            const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
            const ch = (e & f) ^ (~e & g);
            const t1 = (h + S1 + ch + K[i] + W[i]) >>> 0;
            const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
            const mj = (a & b) ^ (a & c) ^ (b & c);
            const t2 = (S0 + mj) >>> 0;
            h = g; g = f; f = e; e = (d + t1) >>> 0;
            d = c; c = b; b = a; a = (t1 + t2) >>> 0;
        }
        H[0] = (H[0] + a) >>> 0; H[1] = (H[1] + b) >>> 0;
        H[2] = (H[2] + c) >>> 0; H[3] = (H[3] + d) >>> 0;
        H[4] = (H[4] + e) >>> 0; H[5] = (H[5] + f) >>> 0;
        H[6] = (H[6] + g) >>> 0; H[7] = (H[7] + h) >>> 0;
    }
    let hex = '';
    for (let i = 0; i < 8; i++) hex += H[i].toString(16).padStart(8, '0');
    return hex;
}

function _utf8Encode(str) {
    if (typeof TextEncoder !== 'undefined') return new TextEncoder().encode(str);
    const bytes = [];
    for (let i = 0; i < str.length; i++) {
        let c = str.charCodeAt(i);
        if (c < 0x80) {
            bytes.push(c);
        } else if (c < 0x800) {
            bytes.push(0xc0 | (c >> 6), 0x80 | (c & 0x3f));
        } else if (c >= 0xd800 && c <= 0xdbff) {
            const c2 = str.charCodeAt(++i);
            const cp = 0x10000 + (((c - 0xd800) << 10) | (c2 - 0xdc00));
            bytes.push(0xf0 | (cp >> 18), 0x80 | ((cp >> 12) & 0x3f),
                       0x80 | ((cp >> 6) & 0x3f), 0x80 | (cp & 0x3f));
        } else {
            bytes.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f));
        }
    }
    return new Uint8Array(bytes);
}

/**
 * 复制文本到剪贴板：优先使用 Clipboard API（仅 Secure Context 可用），
 * 非 Secure Context 退化到 document.execCommand('copy')。
 */
async function copyTextToClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
        try { await navigator.clipboard.writeText(text); return true; } catch (_) { /* 走兜底 */ }
    }
    try {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', '');
        ta.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0;';
        document.body.appendChild(ta);
        ta.select();
        const ok = document.execCommand && document.execCommand('copy');
        ta.remove();
        return !!ok;
    } catch (_) {
        return false;
    }
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
        const ok = await copyTextToClipboard(text);
        copyBtn.textContent = ok ? '已复制' : '复制失败';
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
