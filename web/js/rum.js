/**
 * 腾讯云 RUM（Aegis）前端监控初始化
 *
 * 通过后端下发的 /config.json 中的 `rum` 段配置决定是否启用；
 * 默认关闭，不启用时完全不加载 SDK。
 *
 * 参数对齐腾讯云 RUM 官方接入代码：
 *   new Aegis({ id, uin, spa, reportApiSpeed, reportAssetSpeed, ... })
 */

function initRUM(rumConfig) {
    if (!rumConfig || !rumConfig.enabled) {
        return;
    }
    if (!rumConfig.id) {
        console.warn('RUM enabled but id is empty, skip initialization.');
        return;
    }
    if (window.__aegis) {
        return; // 防止重复初始化
    }

    const src = rumConfig.src || 'https://tam.cdn-go.cn/aegis-sdk/latest/aegis.min.js';
    const script = document.createElement('script');
    script.src = src;
    script.crossOrigin = 'anonymous';
    script.async = true;
    script.onload = function() {
        try {
            if (typeof window.Aegis !== 'function') {
                console.warn('Aegis SDK loaded but global Aegis constructor not found.');
                return;
            }
            // 构造 Aegis 选项：按官方命名映射（snake_case -> camelCase）。
            // hostUrl 是 Aegis SDK 的固定上报端点，SDK 自己内置默认值（腾讯云大陆站
            // 为 https://rumt-zh.com），不是域名白名单，这里不从后端下发，直接用 SDK 默认。
            const options = {
                id: rumConfig.id,
                spa: rumConfig.spa !== false,
                reportApiSpeed: rumConfig.report_api_speed !== false,
                reportAssetSpeed: rumConfig.report_asset_speed !== false,
            };
            if (rumConfig.uin) options.uin = rumConfig.uin;
            if (rumConfig.env) options.env = rumConfig.env;
            if (rumConfig.version) options.version = rumConfig.version;
            if (typeof rumConfig.sample_rate === 'number' && rumConfig.sample_rate < 1) {
                options.sampleRate = rumConfig.sample_rate;
            }
            window.__aegis = new window.Aegis(options);
        } catch (err) {
            console.warn('RUM init failed:', err);
        }
    };
    script.onerror = function(err) {
        console.warn('Failed to load RUM SDK from', src, err);
    };
    document.head.appendChild(script);
}
