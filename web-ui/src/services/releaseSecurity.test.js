import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { runInNewContext } from 'node:vm'

test('logout clears GPS-bearing emergency and drill state while retaining phone history', async () => {
  const source = await readFile(new URL('../auth/authClient.js', import.meta.url), 'utf8')
  const keys = ['landsense_auth_token', 'landsense_auth_refresh_token', 'landsense_auth_profile', 'landsense_offline_emergency_alert_v1', 'landsense_incident_demo_alert', 'landsense_observed_targeted_alerts', 'landsense_previous_phone_numbers']
  const values = new Map(keys.map(key => [key, 'fixture']))
  const clear = runInNewContext(source.replaceAll('export ', '') + '\nclearAuthSession', {
    window: { location: { origin: 'https://fixture.invalid' } },
    localStorage: { removeItem: key => values.delete(key) }
  })
  clear()
  assert.deepEqual([...values.keys()], ['landsense_previous_phone_numbers'])
})
