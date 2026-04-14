/**
 * 管理后台逻辑
 */

import { createProduct, getAdminProducts, offlineProduct, getOrders, uploadIcon } from './api.js'

function $(id) { return document.getElementById(id) }
function hide(el) { el && el.classList.add('hidden') }
function show(el) { el && el.classList.remove('hidden') }

function showMsg(el, msg, isError = false) {
  el.textContent = msg
  el.className = `msg ${isError ? 'msg-error' : 'msg-success'}`
  show(el)
  setTimeout(() => hide(el), 4000)
}

export function initAdmin() {
  initAddProduct()
  initAdminProductList()
  initOrdersQuery()
}

// ── 商品列表（下架）───────────────────────────────────────────────

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
}

async function fetchAdminProducts() {
  const msgEl = $('admin-products-msg')
  const tbody = $('admin-products-tbody')
  const table = $('admin-products-table')
  const empty = $('admin-products-empty')
  hide(msgEl)

  try {
    const res = await getAdminProducts()
    if (res?.code !== 200) {
      showMsg(msgEl, res?.message || '加载失败', true)
      return
    }
    const items = res.data || []
    tbody.innerHTML = ''
    if (!items.length) {
      hide(table)
      show(empty)
      return
    }
    show(table)
    hide(empty)

    items.forEach((p) => {
      const tr = document.createElement('tr')
      const offline = p.offline
      tr.innerHTML = `
        <td>${p.id}</td>
        <td>${escapeHtml(p.key)}</td>
        <td>${escapeHtml(p.title)}</td>
        <td>¥${Number(p.price).toFixed(2)}</td>
        <td>${offline ? '<span class="status-badge status-failed">已下架</span>' : '<span class="status-badge status-paid">上架中</span>'}</td>
        <td>${offline ? '—' : `<button type="button" class="btn-danger btn-offline-product" data-id="${p.id}">下架</button>`}</td>
      `
      tbody.appendChild(tr)
    })

    tbody.querySelectorAll('.btn-offline-product').forEach((btn) => {
      btn.addEventListener('click', () => doOfflineProduct(btn.dataset.id))
    })
  } catch (e) {
    showMsg(msgEl, '网络错误', true)
  }
}

async function doOfflineProduct(productId) {
  const msgEl = $('admin-products-msg')
  if (!confirm('确认下架该商品？前台将不再展示。')) return
  try {
    const res = await offlineProduct(productId)
    if (res?.code === 200) {
      window.dispatchEvent(new CustomEvent('shop-products-updated'))
      await fetchAdminProducts()
      showMsg(msgEl, '已下架', false)
    } else {
      showMsg(msgEl, res?.message || '下架失败', true)
    }
  } catch (e) {
    showMsg(msgEl, '网络错误', true)
  }
}

function initAdminProductList() {
  $('btn-refresh-admin-products')?.addEventListener('click', () => fetchAdminProducts())
}

// ── 新增商品 ──────────────────────────────────────────────────────

function initAddProduct() {
  const btnUpload = $('btn-upload-icon')
  const fileInput = $('admin-icon-file')
  const statusSpan = $('icon-upload-status')

  btnUpload?.addEventListener('click', () => fileInput?.click())

  fileInput?.addEventListener('change', async () => {
    const file = fileInput.files[0]
    if (!file) return
    statusSpan.textContent = '上传中...'
    try {
      const res = await uploadIcon(file)
      if (res?.code === 200) {
        $('admin-icon-url').value = res.data.url
        statusSpan.textContent = '上传成功 ✓'
      } else {
        statusSpan.textContent = `上传失败: ${res?.message || '未知错误'}`
      }
    } catch (e) {
      statusSpan.textContent = '上传失败: 网络错误'
    }
  })

  $('btn-add-product')?.addEventListener('click', async () => {
    const msgEl = $('add-product-msg')

    const payload = {
      key: $('admin-key')?.value?.trim(),
      title: $('admin-title')?.value?.trim(),
      desc: $('admin-desc')?.value,
      price: parseFloat($('admin-price')?.value || '0'),
      expire_time: $('admin-expire')?.value ? parseInt($('admin-expire').value) : null,
      support_continue: $('admin-support-continue')?.checked || false,
      icon: $('admin-icon-url')?.value?.trim() || null,
    }

    if (!payload.key || !payload.title || !payload.price) {
      showMsg(msgEl, 'key、title、price 为必填项', true)
      return
    }

    try {
      const res = await createProduct(payload)
      if (res?.code === 200) {
        showMsg(msgEl, `商品 "${payload.title}" 创建成功`)
        window.dispatchEvent(new CustomEvent('shop-products-updated'))
        fetchAdminProducts()
        // 清空表单
        ;['admin-key', 'admin-title', 'admin-price', 'admin-expire', 'admin-icon-url'].forEach(
          id => { const el = $(id); if (el) el.value = '' }
        )
        $('admin-desc').value = ''
        $('admin-support-continue').checked = false
      } else {
        showMsg(msgEl, res?.message || '创建失败', true)
      }
    } catch (e) {
      showMsg(msgEl, '网络错误', true)
    }
  })
}

// ── 购买记录 ──────────────────────────────────────────────────────

let _currentPage = 1

function initOrdersQuery() {
  $('btn-query-orders')?.addEventListener('click', () => {
    _currentPage = 1
    fetchOrders()
  })
}

async function fetchOrders() {
  const userId = $('filter-user-id')?.value?.trim()
  const status = $('filter-status')?.value || ''

  try {
    const res = await getOrders({
      page: _currentPage, pageSize: 20,
      userId: userId ? parseInt(userId) : undefined,
      status: status || undefined,
    })

    if (res?.code === 200) {
      renderOrders(res.data)
    } else {
      alert(res?.message || '查询失败')
    }
  } catch (e) {
    alert('网络错误')
  }
}

function renderOrders(data) {
  const tbody = $('orders-tbody')
  const table = $('orders-table')
  const empty = $('orders-empty')
  const pagination = $('orders-pagination')

  tbody.innerHTML = ''

  if (!data?.items?.length) {
    hide(table)
    show(empty)
    hide(pagination)
    return
  }

  show(table)
  hide(empty)

  const statusText = { pending: '待支付', paid: '已支付', failed: '失败', refunded: '已退款' }

  data.items.forEach(order => {
    const tr = document.createElement('tr')
    tr.innerHTML = `
      <td title="${order.out_trade_no}">${order.out_trade_no.slice(0, 16)}...</td>
      <td>${order.user_id}</td>
      <td>${order.product_key}</td>
      <td>¥${order.amount.toFixed(2)}</td>
      <td>${order.order_type === 'renew' ? '续费' : '购买'}</td>
      <td><span class="status-badge status-${order.status}">${statusText[order.status] || order.status}</span></td>
      <td>${order.created_at ? order.created_at.replace('T', ' ').replace('Z', '') : ''}</td>
    `
    tbody.appendChild(tr)
  })

  // 分页
  renderPagination(data.total, data.page, data.page_size, pagination)
}

function renderPagination(total, page, pageSize, container) {
  const totalPages = Math.ceil(total / pageSize)
  if (totalPages <= 1) { hide(container); return }

  show(container)
  container.innerHTML = ''

  for (let i = 1; i <= totalPages; i++) {
    const btn = document.createElement('button')
    btn.textContent = i
    btn.className = `page-btn ${i === page ? 'active' : ''}`
    btn.addEventListener('click', () => {
      _currentPage = i
      fetchOrders()
    })
    container.appendChild(btn)
  }
}
