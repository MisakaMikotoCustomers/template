/**
 * API 客户端
 * 自动从 /config.json 加载后端地址，统一注入 Authorization Token
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

// ── 密码哈希 ──────────────────────────────────────────────────────

/**
 * 在发送前对明文密码做 SHA256，返回 64 位十六进制字符串。
 * 使用 Web Crypto API，无需第三方库。
 */
async function hashPassword(plaintext) {
  const encoded = new TextEncoder().encode(plaintext)
  const hashBuffer = await crypto.subtle.digest('SHA-256', encoded)
  return Array.from(new Uint8Array(hashBuffer))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('')
}

// ── 用户接口 ──────────────────────────────────────────────────────

export async function register(username, password) {
  const hashedPassword = await hashPassword(password)
  return request('/user/register', {
    method: 'POST',
    body: JSON.stringify({ username, password: hashedPassword }),
  })
}

export async function login(username, password) {
  const hashedPassword = await hashPassword(password)
  const data = await request('/user/login', {
    method: 'POST',
    body: JSON.stringify({ username, password: hashedPassword }),
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

export async function createProduct(payload) {
  return request('/admin/product', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function getAdminProducts() {
  return request('/admin/products', { method: 'GET' })
}

export async function offlineProduct(productId) {
  return request(`/admin/product/${productId}/offline`, { method: 'POST' })
}

export async function getOrders({ page = 1, pageSize = 20, userId, status } = {}) {
  const params = new URLSearchParams({ page, page_size: pageSize })
  if (userId) params.set('user_id', userId)
  if (status) params.set('status', status)
  return request(`/admin/orders?${params}`, { method: 'GET' })
}

export async function uploadIcon(file) {
  const config = await loadConfig()
  const base = `${config.apiserver.host}${config.apiserver.path_prefix}`
  const token = getToken()
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch(`${base}/admin/upload/icon`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  })
  return res.json()
}

export { loadConfig, getToken }
