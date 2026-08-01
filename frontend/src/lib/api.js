const BASE = '/service/api'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  let body = null
  try {
    body = await res.json()
  } catch {
    // no body
  }
  if (!res.ok) {
    const message = body?.detail || res.statusText || 'Request failed'
    throw new Error(message)
  }
  return body
}

export const api = {
  configStatus: () => request('/config/status'),

  parseCondition: (raw_text) =>
    request('/conditions/parse', { method: 'POST', body: JSON.stringify({ raw_text }) }),

  saveCondition: (rule, raw_text, strategy_key) =>
    request('/conditions/save', {
      method: 'POST',
      body: JSON.stringify({ rule, raw_text, strategy_key }),
    }),

  activeRules: () => request('/rules/active'),

  startMonitor: () => request('/monitor/start', { method: 'POST' }),
  stopMonitor: () => request('/monitor/stop', { method: 'POST' }),
  monitorStatus: () => request('/monitor/status'),

  notifications: (date, order = 'desc') => {
    const params = new URLSearchParams({ order })
    if (date) params.set('date', date)
    return request(`/notifications?${params.toString()}`)
  },
  submitAction: (id, action) =>
    request(`/notifications/${id}/action`, { method: 'POST', body: JSON.stringify({ action }) }),
}
