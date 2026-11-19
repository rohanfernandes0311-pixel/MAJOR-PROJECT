import test from 'node:test'
import assert from 'node:assert/strict'
import {
  buildSimulationMessage,
  estimateSmsSegments,
  isSimulationMessageLanguageEnabled,
} from './simulationMessage.js'
import { SIMULATION_MESSAGE_LOCATIONS_KN } from '../data/simulationMessageTranslations.js'

test('English messages preserve the existing HIGH and CRITICAL text exactly', () => {
  assert.equal(buildSimulationMessage('Madikeri', 'HIGH'), 'SIMULATION ONLY — LANDsense SIMULATION ALERT: High landslide risk simulated in Madikeri. Please stay alert, avoid unstable slopes, and follow the recommended safer route.')
  assert.equal(buildSimulationMessage('Madikeri', 'CRITICAL'), 'SIMULATION ONLY — LANDsense SIMULATION ALERT: Critical landslide risk simulated in Madikeri. Move away from unstable slopes and follow the recommended safer route.')
})

test('Kannada and bilingual templates include the selected place and simulation safeguard', () => {
  const kannada = buildSimulationMessage('Madikeri', 'HIGH', 'kn')
  assert.equal(kannada, 'ಸಿಮ್ಯುಲೇಶನ್ ಮಾತ್ರ — LANDsense ಸಿಮ್ಯುಲೇಶನ್ ಎಚ್ಚರಿಕೆ: ಮಡಿಕೇರಿಯಲ್ಲಿ ಹೆಚ್ಚಿನ ಭೂಕುಸಿತ ಅಪಾಯವನ್ನು ಅನುಕರಿಸಲಾಗಿದೆ. ದಯವಿಟ್ಟು ಎಚ್ಚರಿಕೆಯಿಂದಿರಿ, ಅಸ್ಥಿರ ಇಳಿಜಾರುಗಳಿಂದ ದೂರವಿರಿ ಮತ್ತು ಶಿಫಾರಸು ಮಾಡಿದ ಸುರಕ್ಷಿತ ಮಾರ್ಗವನ್ನು ಅನುಸರಿಸಿ.')
  assert.ok(kannada.startsWith('ಸಿಮ್ಯುಲೇಶನ್ ಮಾತ್ರ'))
  assert.ok(buildSimulationMessage('Unmapped Place', 'HIGH', 'kn').includes('Unmapped Place'))
  const both = buildSimulationMessage('Madikeri', 'HIGH', 'both')
  assert.ok(both.startsWith('SIMULATION ONLY —'))
  assert.ok(both.includes('\nಸಿಮ್ಯುಲೇಶನ್ ಮಾತ್ರ —'))
})

test('LOW and MODERATE templates exist in both languages and every simulation location has a Kannada name', () => {
  for (const risk of ['LOW', 'MODERATE']) {
    assert.ok(buildSimulationMessage('Madikeri', risk).includes(`${risk[0]}${risk.slice(1).toLowerCase()} landslide risk`))
    assert.ok(buildSimulationMessage('Madikeri', risk, 'kn').startsWith('ಸಿಮ್ಯುಲೇಶನ್ ಮಾತ್ರ'))
  }
  assert.deepEqual(Object.keys(SIMULATION_MESSAGE_LOCATIONS_KN).sort(), ['Chittalli', 'Madikeri', 'Makutta', 'Perumbadi', 'Virajpet'].sort())
})

test('SMS estimates use GSM-7 and Unicode single and multipart limits', () => {
  assert.deepEqual(estimateSmsSegments('a'.repeat(160)), { characters: 160, encoding: 'GSM-7', units: 160, singleSegmentLimit: 160, splitSegmentLimit: 153, segments: 1 })
  assert.equal(estimateSmsSegments('a'.repeat(161)).segments, 2)
  assert.equal(estimateSmsSegments('^'.repeat(81)).units, 162)
  assert.equal(estimateSmsSegments('ಕ'.repeat(70)).segments, 1)
  assert.equal(estimateSmsSegments('ಕ'.repeat(71)).segments, 2)
})

test('language feature flag defaults on and can be disabled', () => {
  assert.equal(isSimulationMessageLanguageEnabled(undefined), true)
  assert.equal(isSimulationMessageLanguageEnabled('false'), false)
})
