import { useEffect, useState } from 'react'
import { Activity, Bell, ChevronLeft, LayoutDashboard, LogOut, Map, Menu, ShieldCheck, UserCircle, X } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'
import { maskPhoneNumber } from '../auth/authClient'
import { useAuth } from '../auth/AuthProvider'
import { handleSessionLogout } from './SessionChip'

const ICONS = {
  dashboard: LayoutDashboard,
  map: Map,
  alerts: Bell,
  safety: ShieldCheck,
  overview: LayoutDashboard,
  'risk-zones': Map,
  users: Activity,
  analytics: Activity,
  system: ShieldCheck
}

function LandSenseSidebar({ items, expanded, mobileOpen, onToggle, onNavigate, onClose, profile, onLogout }) {
  const maskedPhone = profile?.phone_number_masked || maskPhoneNumber(profile?.phone_number || '')
  const role = profile?.role ? String(profile.role).replace(/^./, (character) => character.toUpperCase()) : ''
  return (
    <>
      <aside id="landsense-navigation" className={`landsense-sidebar ${expanded ? 'is-expanded' : 'is-collapsed'} ${mobileOpen ? 'is-mobile-open' : ''}`} aria-label="LandSense navigation">
        <div className="landsense-sidebar-header">
          <span className="landsense-brand-mark"><img src="/icons/landsense-logo.png" alt="" /></span>
          <span className="landsense-brand-name">LandSense</span>
          <button type="button" onClick={onClose} className="landsense-mobile-close" aria-label="Close navigation"><X size={18} /></button>
        </div>
        <nav className="landsense-sidebar-nav">
          {items.map((item) => {
            const Icon = item.icon || ICONS[item.id] || LayoutDashboard
            return (
              <a
                key={item.id}
                href={item.href || '#'}
                aria-label={item.label}
                aria-current={item.active ? 'page' : undefined}
                className="landsense-sidebar-link"
                onClick={(event) => {
                  if (item.onClick) {
                    event.preventDefault()
                    item.onClick()
                  }
                  onNavigate()
                }}
              >
                <Icon size={18} strokeWidth={1.8} />
                <span>{item.label}</span>
              </a>
            )
          })}
        </nav>
        <div className="landsense-sidebar-account">
          <div className="landsense-account-details">
            <UserCircle size={20} strokeWidth={1.8} />
            <div>
              {maskedPhone ? <div className="landsense-account-phone">{maskedPhone}</div> : null}
              {role ? <div className="landsense-account-role">{role}</div> : null}
            </div>
          </div>
          <button type="button" onClick={onLogout} className="landsense-account-logout" aria-label="Log out">
            <LogOut size={16} />
            <span>Log out</span>
          </button>
        </div>
        <button type="button" onClick={onToggle} className="landsense-sidebar-toggle" aria-label={expanded ? 'Collapse navigation' : 'Expand navigation'}>
          <ChevronLeft size={17} />
          <span>{expanded ? 'Collapse' : 'Expand'}</span>
        </button>
      </aside>
      {mobileOpen ? <button type="button" className="landsense-sidebar-backdrop" onClick={onClose} aria-label="Close navigation" /> : null}
    </>
  )
}

export default function LandSenseLayout({ items, children }) {
  const [expanded, setExpanded] = useState(true)
  const [mobileOpen, setMobileOpen] = useState(false)
  const navigate = useNavigate()
  const { profile, signOut } = useAuth()
  const closeMobile = () => setMobileOpen(false)

  useEffect(() => {
    if (!mobileOpen) return undefined
    const previousOverflow = document.body.style.overflow
    const previousFocus = document.activeElement
    document.body.style.overflow = 'hidden'
    const drawer = document.getElementById('landsense-navigation')
    const focusable = () => [...drawer.querySelectorAll('a[href], button:not([disabled])')].filter(element => element.getClientRects().length)
    focusable()[0]?.focus()
    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        setMobileOpen(false)
      } else if (event.key === 'Tab') {
        const controls = focusable()
        const first = controls[0]
        const last = controls.at(-1)
        if (event.shiftKey && (document.activeElement === first || !drawer.contains(document.activeElement))) {
          event.preventDefault()
          last?.focus()
        } else if (!event.shiftKey && (document.activeElement === last || !drawer.contains(document.activeElement))) {
          event.preventDefault()
          first?.focus()
        }
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', onKeyDown)
      if (previousFocus?.isConnected) previousFocus.focus()
    }
  }, [mobileOpen])

  return (
    <div className={`landsense-layout ${expanded ? 'sidebar-expanded' : 'sidebar-collapsed'}`}>
      <LandSenseSidebar
        items={items}
        expanded={expanded}
        mobileOpen={mobileOpen}
        onToggle={() => setExpanded((value) => !value)}
        onNavigate={closeMobile}
        onClose={closeMobile}
        profile={profile}
        onLogout={() => handleSessionLogout(signOut, navigate)}
      />
      <button type="button" className="landsense-mobile-trigger" onClick={() => setMobileOpen(true)} aria-label="Open navigation" aria-expanded={mobileOpen} aria-controls="landsense-navigation"><Menu size={20} /></button>
      <div className="landsense-layout-content">{children}</div>
    </div>
  )
}
