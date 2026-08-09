import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { AreaChart, Area, ResponsiveContainer, CartesianGrid, Tooltip, XAxis, YAxis, BarChart, Bar } from 'recharts'
import { BarChart3, ChevronLeft, Home, LayoutDashboard, LogOut, Settings2, User } from 'lucide-react'

const RISK_SCORE = { LOW: 1, MEDIUM: 2, HIGH: 3, CRITICAL: 4, SAFE: 0 }
const ADMIN_KEY_STORAGE = 'landsense_sim_admin_key'
const ADMIN_SESSION_STORAGE = 'landsense_sim_admin_session'
const NAV_ITEMS = [
  { key: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { key: 'overview', label: 'Home', icon: Home },
  { key: 'analytics', label: 'Analytics', icon: BarChart3 },
  { key: 'profile', label: 'Profile', icon: User },
  { key: 'settings', label: 'Settings', icon: Settings2 },
  { key: 'logout', label: 'Logout', icon: LogOut }
]

function toRiskRow(events) {
  const counts = { SAFE: 0, LOW: 0, MEDIUM: 0, HIGH: 0, CRITICAL: 0 }
  events.forEach((evt) => {
    const risk = String(evt.final_risk || '').toUpperCase()
    if (counts[risk] !== undefined) counts[risk] += 1
  })
  return Object.entries(counts).map(([risk, count]) => ({ risk, count }))
}

function toTimeline(events) {
  const ordered = [...events].reverse()
  return ordered.map((evt) => ({
    t: new Date(evt.timestamp_utc).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    score: RISK_SCORE[String(evt.final_risk || '').toUpperCase()] ?? 0,
    rain: Number(evt.rainfall_mm || 0)
  }))
}

export default function Admin() {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [simulationState, setSimulationState] = useState(null)
  const [simulationLoading, setSimulationLoading] = useState(false)
  const [simulationError, setSimulationError] = useState('')
  const [adminKey, setAdminKey] = useState(sessionStorage.getItem(ADMIN_KEY_STORAGE) || '')
  const [adminSession, setAdminSession] = useState(sessionStorage.getItem(ADMIN_SESSION_STORAGE) || '')
  const [forcedRisk, setForcedRisk] = useState('HIGH')
  const [escalationEnabled, setEscalationEnabled] = useState(true)
  const [activeNav, setActiveNav] = useState('dashboard')

  const dashboardRef = useRef(null)
  const analyticsRef = useRef(null)
  const profileRef = useRef(null)
  const settingsRef = useRef(null)
  const eventsRef = useRef(null)

  const sectionRefs = {
    dashboard: dashboardRef,
    overview: dashboardRef,
    analytics: analyticsRef,
    profile: profileRef,
    settings: settingsRef,
    events: eventsRef
  }

  function simulationHeaders() {
    if (adminSession) return { 'X-Simulation-Session': adminSession }
    if (adminKey) return { 'X-Simulation-Admin-Key': adminKey }
    return {}
  }

  async function loadSimulationState() {
    const headers = simulationHeaders()
    if (!Object.keys(headers).length) {
      setSimulationState(null)
      return
    }
    setSimulationError('')
    setSimulationLoading(true)
    try {
      const res = await fetch('/admin/simulation/state', {
        headers
      })
      if (!res.ok) {
        const txt = await res.text()
        throw new Error(txt || 'Unable to load simulation state')
      }
      const json = await res.json()
      setSimulationState(json)
      setForcedRisk(String(json.forced_risk || 'HIGH').toUpperCase() === 'CRITICAL' ? 'CRITICAL' : 'HIGH')
      setEscalationEnabled(Boolean(json.escalation_enabled))
    } catch (err) {
      setSimulationState(null)
      setSimulationError(err?.message || 'Unable to authenticate simulation controls')
    } finally {
      setSimulationLoading(false)
    }
  }

  useEffect(() => {
    let mounted = true

    async function load() {
      setLoading(true)
      try {
        const res = await fetch('/events?limit=60')
        if (!res.ok) return
        const json = await res.json()
        if (!mounted) return
        setEvents(Array.isArray(json.events) ? json.events : [])
      } catch {
        // Keep dashboard visible with empty state.
      } finally {
        if (mounted) setLoading(false)
      }
    }

    load()
    const id = setInterval(load, 30000)
    return () => {
      mounted = false
      clearInterval(id)
    }
  }, [])

  useEffect(() => {
    if (adminSession) {
      sessionStorage.setItem(ADMIN_SESSION_STORAGE, adminSession)
      loadSimulationState()
      return
    }
    sessionStorage.removeItem(ADMIN_SESSION_STORAGE)
    if (adminKey) sessionStorage.setItem(ADMIN_KEY_STORAGE, adminKey)
    else sessionStorage.removeItem(ADMIN_KEY_STORAGE)
  }, [adminSession, adminKey])

  async function authenticateSession() {
    if (!adminKey) {
      setSimulationError('Enter simulation admin key to authenticate.')
      return
    }
    setSimulationError('')
    setSimulationLoading(true)
    try {
      const res = await fetch('/admin/simulation/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ admin_key: adminKey })
      })
      if (!res.ok) {
        const txt = await res.text()
        throw new Error(txt || 'Unable to authenticate simulation session')
      }
      const json = await res.json()
      const token = String(json?.session?.session_token || '')
      if (!token) throw new Error('Missing simulation session token')
      setAdminSession(token)
      await loadSimulationState()
    } catch (err) {
      setAdminSession('')
      setSimulationState(null)
      setSimulationError(err?.message || 'Unable to authenticate simulation session')
    } finally {
      setSimulationLoading(false)
    }
  }

  async function logoutSession() {
    if (adminSession) {
      try {
        await fetch('/admin/simulation/session', {
          method: 'DELETE',
          headers: { 'X-Simulation-Session': adminSession }
        })
      } catch {
        // Continue with local logout even if backend revoke fails.
      }
    }
    setAdminSession('')
    setSimulationState(null)
    setSimulationError('Simulation session logged out.')
  }

  async function updateSimulation(enabled) {
    if (!adminSession && !adminKey) {
      setSimulationError('Authenticate simulation session first.')
      return
    }
    setSimulationError('')
    setSimulationLoading(true)
    try {
      const res = await fetch('/admin/simulation/state', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...simulationHeaders()
        },
        body: JSON.stringify({
          enabled,
          forced_risk: forcedRisk,
          escalation_enabled: escalationEnabled,
          scenario_name: 'Demo Danger Mode'
        })
      })
      if (!res.ok) {
        const txt = await res.text()
        throw new Error(txt || 'Unable to update simulation mode')
      }
      const json = await res.json()
      setSimulationState(json.state)
    } catch (err) {
      setSimulationError(err?.message || 'Unable to update simulation mode')
    } finally {
      setSimulationLoading(false)
    }
  }

  function handleNavClick(key) {
    if (key === 'logout') {
      logoutSession()
      return
    }

    setActiveNav(key)
    const target = sectionRefs[key]?.current
    if (target?.scrollIntoView) {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' })
    } else if (key === 'dashboard' || key === 'overview') {
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }

  const timeline = useMemo(() => toTimeline(events), [events])
  const riskBreakdown = useMemo(() => toRiskRow(events), [events])
  const highRiskCount = useMemo(() => events.filter((evt) => String(evt.final_risk).toUpperCase() === 'HIGH').length, [events])
  const avgRainfall = useMemo(() => {
    if (!events.length) return 0
    const total = events.reduce((sum, evt) => sum + Number(evt.rainfall_mm || 0), 0)
    return total / events.length
  }, [events])

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(34,211,238,0.12),_transparent_28%),linear-gradient(180deg,_#06111b_0%,_#091421_100%)] px-4 py-4 text-white sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[1600px] lg:grid lg:grid-cols-[290px_minmax(0,1fr)] lg:gap-6">
        <aside className="mb-4 overflow-hidden rounded-[28px] border border-white/8 bg-[#0b1522]/95 shadow-[0_20px_80px_rgba(3,7,18,0.45)] backdrop-blur xl:sticky xl:top-6 xl:mb-0 xl:h-[calc(100vh-3rem)]">
          <div className="flex h-full flex-col">
            <div className="flex items-center justify-between border-b border-white/8 px-5 py-5">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[linear-gradient(135deg,#22c1ff_0%,#7c3aed_55%,#c026d3_100%)] text-sm font-black text-white shadow-lg shadow-cyan-500/20">
                  L
                </div>
                <div>
                  <div className="text-xl font-bold tracking-tight text-white">Land Sense</div>
                  <div className="text-xs uppercase tracking-[0.22em] text-slate-400">Command Center</div>
                </div>
              </div>
              <div className="flex h-9 w-9 items-center justify-center rounded-full border border-white/8 bg-white/5 text-slate-400">
                <ChevronLeft className="h-4 w-4" />
              </div>
            </div>

            <nav className="flex-1 px-4 py-5">
              <div className="space-y-2">
                {NAV_ITEMS.map((item) => {
                  const Icon = item.icon
                  const isActive = activeNav === item.key
                  return (
                    <button
                      key={item.key}
                      type="button"
                      onClick={() => handleNavClick(item.key)}
                      className={`group flex w-full items-center justify-between rounded-2xl px-4 py-4 text-left transition ${
                        isActive
                          ? 'bg-[linear-gradient(135deg,#2563eb_0%,#7c3aed_55%,#c026d3_100%)] text-white shadow-lg shadow-violet-500/20'
                          : 'text-slate-300 hover:bg-white/5 hover:text-white'
                      }`}
                    >
                      <div className="flex items-center gap-4">
                        <span className={`flex h-9 w-9 items-center justify-center rounded-xl ${isActive ? 'bg-white/12' : 'bg-white/5'}`}>
                          <Icon className="h-5 w-5" />
                        </span>
                        <span className="text-lg font-semibold tracking-tight">{item.label}</span>
                      </div>
                      {isActive ? <span className="h-3 w-3 rounded-full bg-white/80 shadow-[0_0_0_6px_rgba(255,255,255,0.12)]" /> : null}
                    </button>
                  )
                })}
              </div>

              <div ref={profileRef} className="mt-6 rounded-[24px] border border-white/8 bg-[#08101a] p-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[linear-gradient(135deg,#06b6d4_0%,#22c55e_100%)] text-sm font-bold text-white">
                    LS
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-white">LandSense Operator</div>
                    <div className="text-sm text-slate-400">{adminSession ? 'Simulation authenticated' : 'Monitoring session ready'}</div>
                  </div>
                </div>
                <div className="mt-4 rounded-2xl border border-white/8 bg-white/5 px-3 py-2 text-xs text-slate-300">
                  {adminSession ? 'Secure simulation session active.' : 'Authenticate to unlock emergency simulation controls.'}
                </div>
              </div>
            </nav>
          </div>
        </aside>

        <main className="space-y-6">
          {simulationState?.enabled ? (
            <div className="rounded-2xl border border-amber-300/40 bg-amber-500/15 px-4 py-3 text-amber-100">
              <div className="text-xs font-semibold tracking-[0.24em]">SIMULATION MODE ACTIVE</div>
              <div className="mt-1 text-sm">
                Emergency simulation is active with effective risk {simulationState.effective_risk || simulationState.forced_risk}.
              </div>
            </div>
          ) : null}

          <section ref={dashboardRef} className="rounded-[28px] border border-white/8 bg-[#0c1724]/90 p-5 shadow-[0_20px_80px_rgba(3,7,18,0.28)] backdrop-blur">
            <header className="flex flex-col gap-4 border-b border-white/8 pb-5 xl:flex-row xl:items-end xl:justify-between">
              <div>
                <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-cyan-300/20 bg-cyan-400/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.24em] text-cyan-100">
                  <span className="h-2 w-2 rounded-full bg-cyan-300" />
                  LandSense live monitoring
                </div>
                <h1 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">Admin Dashboard</h1>
                <div className="mt-2 max-w-2xl text-sm text-slate-300">
                  Realtime analytics from the active backend event stream, presented in a LandSense control layout without changing the underlying workflow.
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <Link
                  to="/demo"
                  className="rounded-full border border-red-300/30 bg-red-400/15 px-4 py-2 text-sm font-semibold text-red-100 transition hover:bg-red-400/20"
                >
                  Launch Demo Mode
                </Link>
                <div className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200">
                  {loading ? 'Refreshing data...' : `Loaded ${events.length} events`}
                </div>
              </div>
            </header>

            <section ref={settingsRef} className="mt-6 rounded-[24px] border border-white/8 bg-[#08101a] p-4">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-white">Emergency Test Controls</div>
                  <div className="text-xs text-slate-400">Simulation-only control surface for the existing admin workflow.</div>
                </div>
                <div className="rounded-full border border-white/8 bg-white/5 px-3 py-1.5 text-xs text-slate-300">
                  {simulationState?.enabled ? 'Demo danger mode active' : 'Live monitoring mode'}
                </div>
              </div>
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1.4fr_auto_1fr_1fr_auto_auto]">
                <input
                  type="password"
                  value={adminKey}
                  onChange={(e) => setAdminKey(e.target.value)}
                  placeholder="Simulation admin key"
                  className="rounded-xl border border-white/10 bg-[#07101a] px-3 py-2 text-sm text-white outline-none focus:border-cyan-300/40"
                />

                <button
                  type="button"
                  disabled={simulationLoading}
                  onClick={authenticateSession}
                  className="rounded-xl border border-cyan-300/30 bg-cyan-400/15 px-4 py-2 text-sm font-semibold text-cyan-100 disabled:opacity-50"
                >
                  Authenticate
                </button>

                <select
                  value={forcedRisk}
                  onChange={(e) => setForcedRisk(e.target.value)}
                  className="rounded-xl border border-white/10 bg-[#07101a] px-3 py-2 text-sm text-white outline-none focus:border-cyan-300/40"
                >
                  <option value="HIGH">HIGH</option>
                  <option value="CRITICAL">CRITICAL</option>
                </select>

                <label className="flex items-center gap-2 rounded-xl border border-white/10 bg-[#07101a] px-3 py-2 text-sm text-slate-100">
                  <input
                    type="checkbox"
                    checked={escalationEnabled}
                    onChange={(e) => setEscalationEnabled(e.target.checked)}
                  />
                  Escalate to CRITICAL
                </label>

                <button
                  type="button"
                  disabled={simulationLoading}
                  onClick={() => updateSimulation(false)}
                  className="rounded-xl border border-emerald-300/30 bg-emerald-400/15 px-4 py-2 text-sm font-semibold text-emerald-100 disabled:opacity-50"
                >
                  Live Monitoring
                </button>

                <button
                  type="button"
                  disabled={simulationLoading}
                  onClick={() => updateSimulation(true)}
                  className="rounded-xl border border-red-300/30 bg-red-400/15 px-4 py-2 text-sm font-semibold text-red-100 disabled:opacity-50"
                >
                  Demo Danger Mode
                </button>
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-2">
                <div className="text-xs text-slate-300">
                  Session: {adminSession ? 'Authenticated' : 'Not authenticated'}
                </div>
                {adminSession ? (
                  <button
                    type="button"
                    onClick={logoutSession}
                    className="rounded-lg border border-white/15 bg-white/5 px-3 py-1.5 text-xs font-semibold text-slate-200"
                  >
                    Logout session
                  </button>
                ) : null}
              </div>

              <div className="mt-3 text-xs text-slate-300">
                {simulationLoading
                  ? 'Updating simulation state...'
                  : simulationState
                    ? `Mode: ${simulationState.enabled ? 'Simulation active' : 'Live monitoring'} | Zone: ${simulationState.danger_zone_id || '-'} | External notifications ${simulationState.external_notifications_suppressed ? 'suppressed' : 'allowed'}`
                    : 'Authenticate with the simulation admin key to unlock secure simulation controls.'}
              </div>
              {simulationError ? <div className="mt-2 text-xs text-rose-300">{simulationError}</div> : null}
            </section>

            <section className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-3">
              <div className="rounded-2xl border border-white/10 bg-[#0c1724] p-4">
                <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Operator</div>
                <div className="mt-2 text-3xl font-bold">LandSense</div>
                <div className="mt-1 text-sm text-slate-300">Command center overview for the current monitoring session.</div>
              </div>
              <div className="rounded-2xl border border-white/10 bg-[#0c1724] p-4">
                <div className="text-xs uppercase tracking-[0.2em] text-slate-400">High risk alerts</div>
                <div className="mt-2 text-3xl font-bold text-red-300">{highRiskCount}</div>
              </div>
              <div className="rounded-2xl border border-white/10 bg-[#0c1724] p-4">
                <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Avg rainfall</div>
                <div className="mt-2 text-3xl font-bold">{avgRainfall.toFixed(1)} mm</div>
              </div>
            </section>
          </section>

          <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <div ref={analyticsRef} className="rounded-2xl border border-white/10 bg-[#0c1724] p-4">
              <div className="mb-3 text-sm font-semibold">Risk trend</div>
              <div className="h-72 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={timeline}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.2)" />
                    <XAxis dataKey="t" tick={{ fill: '#cbd5e1', fontSize: 12 }} minTickGap={25} />
                    <YAxis tick={{ fill: '#cbd5e1', fontSize: 12 }} domain={[0, 4]} />
                    <Tooltip />
                    <Area type="monotone" dataKey="score" stroke="#fb7185" fill="rgba(251,113,133,0.25)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="rounded-2xl border border-white/10 bg-[#0c1724] p-4">
              <div className="mb-3 text-sm font-semibold">Risk distribution</div>
              <div className="h-72 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={riskBreakdown}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.2)" />
                    <XAxis dataKey="risk" tick={{ fill: '#cbd5e1', fontSize: 12 }} />
                    <YAxis tick={{ fill: '#cbd5e1', fontSize: 12 }} />
                    <Tooltip />
                    <Bar dataKey="count" fill="#38bdf8" radius={[8, 8, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </section>

          <section ref={eventsRef} className="rounded-2xl border border-white/10 bg-[#0c1724] p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold">Recent events</div>
                <div className="text-xs text-slate-400">Latest backend records shown in the same workflow, now wrapped in the LandSense visual language.</div>
              </div>
              <div className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-300">
                {loading ? 'Refreshing data...' : `Loaded ${events.length} events`}
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="border-b border-white/10 text-slate-300">
                  <tr>
                    <th className="px-3 py-2">Time</th>
                    <th className="px-3 py-2">User</th>
                    <th className="px-3 py-2">Risk</th>
                    <th className="px-3 py-2">Rainfall</th>
                    <th className="px-3 py-2">Zone</th>
                  </tr>
                </thead>
                <tbody>
                  {events.slice(0, 12).map((evt) => (
                    <tr key={evt.id} className="border-b border-white/5 text-slate-200">
                      <td className="px-3 py-2">{new Date(evt.timestamp_utc).toLocaleString()}</td>
                      <td className="px-3 py-2">{evt.user_id}</td>
                      <td className="px-3 py-2">{evt.final_risk}</td>
                      <td className="px-3 py-2">{Number(evt.rainfall_mm).toFixed(1)} mm</td>
                      <td className="px-3 py-2">{evt.active_zone_id || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </main>
      </div>
    </div>
  )
}
