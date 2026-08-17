import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

test('admin targeted SMS control is explicit, default-off, and shows eligible count', async () => {
  const source = await readFile(new URL('../pages/Admin.jsx', import.meta.url), 'utf8')

  assert.match(source, /const \[sendSms, setSendSms\] = useState\(false\)/)
  assert.match(source, /Send SMS to eligible users/)
  assert.match(source, /Eligible SMS recipients:/)
  assert.match(source, /In-app alert will always be created/)
  assert.match(source, /Simulation mode — SMS suppressed/)
  assert.match(source, /send_sms: sendSms/)
})
