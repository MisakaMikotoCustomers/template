/**
 * 登录 / 注册 页面逻辑
 */

(async function () {
    // 已登录直接跳回主页
    if (getToken()) {
        location.href = 'home.html';
        return;
    }

    // 应用品牌名（从 config.json 读取）
    await initAPIConfig();
    // 根据下发的 RUM 配置按需初始化 Aegis；未启用或缺失时为 no-op。
    if (typeof initRUM === 'function') {
        initRUM(window.__RUM_CONFIG__);
    }
    const brandName = getAppName();
    document.title = `登录 · ${brandName}`;
    const brandEl = document.getElementById('authBrand');
    if (brandEl) brandEl.textContent = brandName;

    let mode = 'login'; // 'login' | 'register'

    const $ = id => document.getElementById(id);
    const form = $('authForm');
    const nameInput = $('nameInput');
    const passwordInput = $('passwordInput');
    const submitBtn = $('submitBtn');
    const hintEl = $('authHint');
    const subtitle = $('authSubtitle');
    const switchLabel = $('switchLabel');
    const switchLink = $('switchLink');

    function setMode(next) {
        mode = next;
        if (mode === 'login') {
            subtitle.textContent = '登录你的账号';
            submitBtn.textContent = '登录';
            switchLabel.textContent = '还没有账号？';
            switchLink.textContent = '去注册';
        } else {
            subtitle.textContent = '创建新账号';
            submitBtn.textContent = '注册';
            switchLabel.textContent = '已经有账号？';
            switchLink.textContent = '去登录';
        }
        hintEl.textContent = '';
    }

    switchLink.addEventListener('click', () => {
        setMode(mode === 'login' ? 'register' : 'login');
    });

    form.addEventListener('submit', async (ev) => {
        ev.preventDefault();
        hintEl.textContent = '';
        const name = nameInput.value.trim();
        const password = passwordInput.value;
        if (!name || !password) {
            hintEl.textContent = '请输入用户名和密码';
            return;
        }

        submitBtn.disabled = true;
        try {
            const passwordHash = await hashPassword(password);
            const api = mode === 'login' ? userAPI.login : userAPI.register;
            const resp = await api(name, passwordHash);
            saveAuth(resp.data);
            location.href = 'home.html';
        } catch (e) {
            hintEl.textContent = e.message || '操作失败，请稍后重试';
        } finally {
            submitBtn.disabled = false;
        }
    });

    setMode('login');
})();
