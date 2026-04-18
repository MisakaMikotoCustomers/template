/**
 * API 调用封装
 *
 * - 从 /config.json（由容器启动时根据 config.toml 生成）读取后端地址、展示名
 * - 所有请求自动带 Authorization / traceId / Content-Type
 * - 401 自动清空本地登录态并跳回登录页
 */

let API_BASE = '/api';
let APP_NAME = 'Template';
let API_READY = null;

async function initAPIConfig() {
    if (API_READY) return API_READY;
    API_READY = (async () => {
        try {
            const resp = await fetch('config.json', { cache: 'no-store' });
            if (resp.ok) {
                const config = await resp.json();
                if (config) {
                    if (config.server && config.server.name) {
                        APP_NAME = config.server.name;
                    }
                    if (config.apiserver) {
                        const host = (config.apiserver.host || '').replace(/\/$/, '');
                        const prefix = config.apiserver.path_prefix || '/api';
                        // host 留空 -> 同域，直接用 prefix
                        API_BASE = (host || '') + prefix;
                    }
                }
            }
        } catch (e) {
            console.warn('Failed to load config.json, fallback to', API_BASE, e);
        }
    })();
    return API_READY;
}

function getAppName() { return APP_NAME; }

async function request(path, options = {}) {
    await initAPIConfig();
    const token = getToken();
    const headers = {
        'Content-Type': 'application/json',
        'traceId': generateUUID(),
        ...(options.headers || {}),
    };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    let resp;
    try {
        resp = await fetch(API_BASE + path, { ...options, headers });
    } catch (e) {
        throw new Error('网络连接失败，请稍后重试');
    }

    let data = null;
    try { data = await resp.json(); } catch (_) { data = null; }

    if (!resp.ok) {
        if (resp.status === 401) {
            clearAuth();
            if (!/index\.html$/.test(location.pathname) && location.pathname !== '/') {
                location.href = 'index.html';
            }
        }
        const msg = (data && (data.message || data.error)) || `请求失败 (${resp.status})`;
        const err = new Error(msg);
        err.code = (data && data.code) || resp.status;
        throw err;
    }
    return data;
}

const userAPI = {
    async register(name, passwordHash) {
        return request('/app/user/register', {
            method: 'POST',
            body: JSON.stringify({ name, password_hash: passwordHash }),
        });
    },
    async login(name, passwordHash) {
        return request('/app/user/login', {
            method: 'POST',
            body: JSON.stringify({ name, password_hash: passwordHash }),
        });
    },
    async me() { return request('/app/user/me'); },
    async logout() { return request('/app/user/logout', { method: 'POST' }); },
};

const feedbackAPI = {
    async list(page = 1, pageSize = 20) {
        return request(`/app/feedback?page=${page}&page_size=${pageSize}`);
    },
    async create(content) {
        return request('/app/feedback', {
            method: 'POST',
            body: JSON.stringify({ content }),
        });
    },
    async detail(key) {
        return request(`/app/feedback/${encodeURIComponent(key)}`);
    },
    async sendMessage(key, content) {
        return request(`/app/feedback/${encodeURIComponent(key)}/messages`, {
            method: 'POST',
            body: JSON.stringify({ content }),
        });
    },
};

const adminAPI = {
    async listFeedback(page = 1, pageSize = 20, status = '') {
        let url = `/admin/feedback?page=${page}&page_size=${pageSize}`;
        if (status) url += `&status=${encodeURIComponent(status)}`;
        return request(url);
    },
    async feedbackDetail(userId, key) {
        return request(`/admin/feedback/${userId}/${encodeURIComponent(key)}`);
    },
    async reply(userId, key, content) {
        return request(`/admin/feedback/${userId}/${encodeURIComponent(key)}/messages`, {
            method: 'POST',
            body: JSON.stringify({ content }),
        });
    },
    async changeStatus(userId, key, status) {
        return request(`/admin/feedback/${userId}/${encodeURIComponent(key)}/status`, {
            method: 'PATCH',
            body: JSON.stringify({ status }),
        });
    },
};
