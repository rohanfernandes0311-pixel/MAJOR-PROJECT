import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../../', import.meta.url))
const source = (path) => readFileSync(`${root}${path}`, 'utf8')

test('admin loads configured zones from the authenticated API and keeps selection state separate', () => {
  const admin = source('src/pages/Admin.jsx')
  assert.match(admin, /apiFetch\('\/zones', \{\}, token\)/)
  assert.match(admin, /selectedConfiguredZone/)
  assert.match(admin, /selectedIncidentScenario/)
  assert.match(admin, /if \(value\) setSelectedIncidentScenario\(''\)/)
  assert.match(admin, /if \(value\) setSelectedConfiguredZone\(''\)/)
  assert.doesNotMatch(admin, /current \|\| String\(configuredZones\[0\]/)
})

test('configured selection passes actual geometry to a map that fits its bounds', () => {
  const admin = source('src/pages/Admin.jsx')
  const map = source('src/shared/MapView.jsx')
  assert.match(admin, /selectedZone=\{selectedConfiguredZoneGeometry\}/)
  assert.match(map, /selectedLayer\.getBounds\(\)/)
  assert.match(map, /map\.fitBounds\(selectedBounds/)
  assert.match(admin, /Selection only — no alert has been activated\./)
})

test('OTP edit preserves the current number but resets the pending verification attempt', () => {
  const otp = source('src/pages/OTP.jsx')
  const authService = source('src/services/authService.js')
  assert.match(otp, /resetPhoneSignIn\(\)/)
  assert.match(otp, /editPhoneNumber: phoneToEdit/)
  assert.match(authService, /confirmationResultRef = null/)
  assert.match(authService, /clearPendingFirebaseSignIn\(\)/)
})
