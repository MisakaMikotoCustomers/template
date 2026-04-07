/**
 * API 客户端
 * 自动从 /config.json 加载后端地址，注入 Authorization Token
 */

let _config = null

async function loadConfig() {
  if (_config) return _config
  const res = await fetch('/config.json')
  _config = await res.json()
  return _config
}

function getToken() {
  return localStorage.getItem('shop_token') || ''
}

function setToken(token) {
  localStorage.setItem('shop_token', token)
}

function clearToken() {
  localStorage.removeItem('shop_token')
  localStorage.removeItem('shop_user')
}

async function request(path, options = {}) {
  const config = await loadConfig()
  const base = `${config.apiserver.host}${config.apiserver.path_prefix}`
  const url = `${base}${path}`

  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) }
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(url, { ...options, headers })

  if (res.status === 401) {
    clearToken()
    window.location.reload()
    return
  }

  const data = await res.json()
  return data
}

async function adminRequest(path, options = {}, adminToken) {
  const config = await loadConfig()
  const base = `${config.apiserver.host}${config.apiserver.path_prefix}`
  const url = `${base}${path}`

  const headers = {
    'Content-Type': 'application/json',
    'X-Admin-Token': adminToken || '',
    ...(options.headers || {}),
  }

  const res = await fetch(url, { ...options, headers })
  return res.json()
}

// ── 用户接口 ──────────────────────────────────────────────────────

export async function register(username, password) {
  return request('/user/register', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export async function login(username, password) {
  const data = await request('/user/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
  if (data?.code === 200) {
    setToken(data.data.token)
    localStorage.setItem('shop_user', JSON.stringify(data.data.user))
  }
  return data
}

export function logout() {
  clearToken()
}

export function getCurrentUser() {
  const raw = localStorage.getItem('shop_user')
  return raw ? JSON.parse(raw) : null
}

// ── 商品接口 ──────────────────────────────────────────────────────

export async function getProducts() {
  return request('/commercial/products')
}

export async function buyProduct(productId, orderType = 'purchase', device = null) {
  return request('/commercial/buy', {
    method: 'POST',
    body: JSON.stringify({ product_id: productId, order_type: orderType, device }),
  })
}

// ── 管理接口 ──────────────────────────────────────────────────────

export async function createProduct(adminToken, payload) {
  return adminRequest('/admin/product', {
    method: 'POST',
    body: JSON.stringify(payload),
  }, adminToken)
}

export async function getOrders(adminToken, { page = 1, pageSize = 20, userId, status } = {}) {
  const params = new URLSearchParams({ page, page_size: pageSize })
  if (userId) params.set('user_id', userId)
  if (status) params.set('status', status)
  return adminRequest(`/admin/orders?${params}`, { method: 'GET' }, adminToken)
}

export async function uploadIcon(adminToken, file) {
  const config = await loadConfig()
  const base = `${config.apiserver.host}${config.apiserver.path_prefix}`
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch(`${base}/admin/upload/icon`, {
    method: 'POST',
    headers: { 'X-Admin-Token': adminToken || '' },
    body: formData,
  })
  return res.json()
}

export { loadConfig, getToken }
