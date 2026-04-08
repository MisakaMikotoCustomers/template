/**
 * 商品支付模板 - 主入口
 * 构建版本: __BUILD_TAG__ (由 Vite 编译时注入)
 */

import './style.css'
import {
  loadConfig, getCurrentUser, login, register, logout,
  getProducts, buyProduct,
} from './api.js'
import { initAdmin } from './admin.js'

const BUILD_TAG = typeof __BUILD_TAG__ !== 'undefined' ? __BUILD_TAG__ : 'dev'
console.info(`Shop Web v${BUILD_TAG}`)

// ── 工具函数 ──────────────────────────────────────────────────────

function showToast(msg, type = 'info') {
  const container = document.getElementById('toast-container')
  const el = document.createElement('div')
  el.className = `toast toast-${type}`
  el.textContent = msg
  container.appendChild(el)
  setTimeout(() => el.classList.add('show'), 10)
  setTimeout(() => {
    el.classList.remove('show')
    setTimeout(() => el.remove(), 300)
  }, 3000)
}

function $(id) { return document.getElementById(id) }
function hide(el) { el && el.classList.add('hidden') }
function show(el) { el && el.classList.remove('hidden') }

// ── 鉴权状态更新 ─────────────────────────────────────────────────

function updateAuthUI() {
  const user = getCurrentUser()
  if (user) {
    show($('nav-auth'))
    hide($('nav-login-link'))
    $('nav-username').textContent = user.username
  } else {
    hide($('nav-auth'))
    show($('nav-login-link'))
  }
}

// ── 登录/注册 ─────────────────────────────────────────────────────

function openAuthModal() { show($('modal-auth')) }
function closeAuthModal() { hide($('modal-auth')) }

function initAuthModal() {
  $('modal-overlay').addEventListener('click', closeAuthModal)
  $('btn-show-login').addEventListener('click', openAuthModal)

  // 标签切换
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'))
      document.querySelectorAll('.tab-panel').forEach(p => hide(p))
      btn.classList.add('active')
      show($(`panel-${btn.dataset.tab}`))
    })
  })

  // 登录
  $('btn-login').addEventListener('click', async () => {
    const username = $('login-username').value.trim()
    const password = $('login-password').value
    hide($('login-error'))
    if (!username || !password) return

    const res = await login(username, password)
    if (res?.code === 200) {
      closeAuthModal()
      updateAuthUI()
      await loadProducts()
      showToast('登录成功', 'success')
    } else {
      $('login-error').textContent = res?.message || '登录失败'
      show($('login-error'))
    }
  })

  // 注册
  $('btn-register').addEventListener('click', async () => {
    const username = $('reg-username').value.trim()
    const password = $('reg-password').value
    hide($('reg-error'))
    if (!username || !password) return
    if (password.length < 6) {
      $('reg-error').textContent = '密码至少6位'
      show($('reg-error'))
      return
    }

    const res = await register(username, password)
    if (res?.code === 200) {
      closeAuthModal()
      updateAuthUI()
      await loadProducts()
      showToast('注册成功', 'success')
    } else {
      $('reg-error').textContent = res?.message || '注册失败'
      show($('reg-error'))
    }
  })

  // 退出
  $('btn-logout').addEventListener('click', () => {
    logout()
    updateAuthUI()
    showToast('已退出登录')
    renderProducts([])
  })
}

// ── 商品列表 ──────────────────────────────────────────────────────

function renderProducts(products) {
  const grid = $('products-grid')
  const empty = $('products-empty')
  grid.innerHTML = ''

  if (!products || products.length === 0) {
    show(empty)
    return
  }
  hide(empty)

  products.forEach(p => {
    const card = document.createElement('div')
    card.className = 'product-card'
    card.innerHTML = `
      ${p.icon ? `<img src="${p.icon}" class="product-icon" alt="${p.title}" />` : '<div class="product-icon-placeholder"></div>'}
      <div class="product-body">
        <h3 class="product-title">${escapeHtml(p.title)}</h3>
        <div class="product-desc">${p.desc || ''}</div>
        <div class="product-price">¥${p.price.toFixed(2)}</div>
        ${p.expire_time ? `<div class="product-expire">有效期 ${formatDuration(p.expire_time)}</div>` : '<div class="product-expire">永久有效</div>'}
        <div class="product-actions">
          <button class="btn-primary btn-buy" data-id="${p.id}" data-type="purchase">立即购买</button>
          ${p.support_continue ? `<button class="btn-secondary btn-renew" data-id="${p.id}" data-type="renew">续费</button>` : ''}
        </div>
      </div>
    `
    grid.appendChild(card)
  })

  // 购买/续费点击
  grid.querySelectorAll('.btn-buy, .btn-renew').forEach(btn => {
    btn.addEventListener('click', () => handleBuy(btn.dataset.id, btn.dataset.type))
  })
}

async function loadProducts() {
  const res = await getProducts()
  if (res?.code === 200) {
    renderProducts(res.data || [])
  } else {
    showToast('加载商品失败', 'error')
  }
}

async function handleBuy(productId, orderType) {
  const user = getCurrentUser()
  if (!user) {
    openAuthModal()
    showToast('请先登录', 'warning')
    return
  }

  try {
    const res = await buyProduct(productId, orderType)
    if (res?.code === 200) {
      window.location.href = res.data.pay_url
    } else {
      showToast(res?.message || '生成支付链接失败', 'error')
    }
  } catch (e) {
    showToast('网络错误', 'error')
  }
}

// ── 工具 ──────────────────────────────────────────────────────────

function escapeHtml(str) {
  return str.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
}

function formatDuration(seconds) {
  if (seconds >= 86400 * 365) return `${Math.round(seconds / (86400 * 365))} 年`
  if (seconds >= 86400 * 30) return `${Math.round(seconds / (86400 * 30))} 个月`
  if (seconds >= 86400) return `${Math.round(seconds / 86400)} 天`
  return `${Math.round(seconds / 3600)} 小时`
}

// ── 初始化 ────────────────────────────────────────────────────────

async function init() {
  const config = await loadConfig()

  updateAuthUI()
  initAuthModal()

  // 显示商业化相关区块（始终开启）
  document.querySelectorAll('.business-only').forEach(el => show(el))
  await loadProducts()
  initAdmin()

  window.addEventListener('shop-products-updated', () => {
    loadProducts().catch(console.error)
  })
}

init().catch(console.error)
