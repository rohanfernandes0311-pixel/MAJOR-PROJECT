const STORAGE_KEY = 'landsense_observed_targeted_alerts'
const MAX_OBSERVED_ALERTS = 500

function alertKey(alert) {
  if (alert?.id !== undefined && alert?.id !== null) return String(alert.id)
  return `${alert?.timestamp || ''}|${alert?.risk_level || ''}|${alert?.message || ''}`
}

function isSimulationAlert(alert) {
  return (
    String(alert?.source_type || '').toUpperCase().includes('SIMULATION') ||
    alert?.simulation === true ||
    /^\s*SIMULAT(?:ED|ION) ALERT\b/i.test(String(alert?.message || ''))
  )
}

export function buildNotificationContent(alert) {
  const risk = String(alert?.risk_level || 'RISK ALERT').trim().toUpperCase()
  const simulation = isSimulationAlert(alert)
  const message = String(alert?.message || 'A targeted alert has been issued for your area.').trim()

  return {
    title: simulation ? 'LANDSENSE DEMO ALERT' : `LANDSense — ${risk}`,
    body: message.length > 240 ? `${message.slice(0, 237)}...` : message,
    tag: `landsense-targeted-${alertKey(alert)}`,
    data: { url: '/#targeted-alerts' },
    actions: [{ action: 'open-dashboard', title: 'Open Dashboard' }]
  }
}

export class AlertNotificationManager {
  constructor({ storage = globalThis.localStorage, showNotification } = {}) {
    this.storage = storage
    this.showNotification = showNotification || this.showWithServiceWorker.bind(this)
    this.observedKeys = this.loadObservedKeys()
  }

  loadObservedKeys() {
    try {
      const parsed = JSON.parse(this.storage?.getItem(STORAGE_KEY) || '[]')
      return new Set(Array.isArray(parsed) ? parsed.map(String) : [])
    } catch {
      return new Set()
    }
  }

  saveObservedKeys() {
    try {
      const keys = Array.from(this.observedKeys).slice(-MAX_OBSERVED_ALERTS)
      this.observedKeys = new Set(keys)
      this.storage?.setItem(STORAGE_KEY, JSON.stringify(keys))
    } catch {
      // Browser storage may be unavailable; in-memory duplicate prevention remains active.
    }
  }

  markObserved(alert) {
    this.observedKeys.add(alertKey(alert))
    this.saveObservedKeys()
  }

  hasBeenObserved(alert) {
    return this.observedKeys.has(alertKey(alert))
  }

  async showWithServiceWorker(title, options) {
    if (!('serviceWorker' in navigator)) throw new Error('Service workers are unavailable')
    const registration = await navigator.serviceWorker.ready
    await registration.showNotification(title, options)
  }

  async observe(alerts, { notify = false } = {}) {
    const newlyObserved = (Array.isArray(alerts) ? alerts : []).filter((alert) => !this.hasBeenObserved(alert))

    for (const alert of newlyObserved) {
      if (!notify) {
        this.markObserved(alert)
        continue
      }

      const content = buildNotificationContent(alert)
      try {
        await this.showNotification(content.title, {
          body: content.body,
          tag: content.tag,
          data: content.data,
          actions: content.actions,
          renotify: false
        })
        this.markObserved(alert)
      } catch {
        // Leave the alert unobserved so a later refresh can retry browser display.
      }
    }

    return newlyObserved.length
  }
}

export const alertNotificationStorageKey = STORAGE_KEY
