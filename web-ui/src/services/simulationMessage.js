import {
  SIMULATION_MESSAGE_LOCATIONS_KN,
  SIMULATION_MESSAGE_TEMPLATES,
} from '../data/simulationMessageTranslations.js'

const GSM7_BASIC = new Set('@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\fÆæßÉ !"#¤%&\'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà')
const GSM7_EXTENSION = new Set('^{}\\[~]|€\f')

export function isSimulationMessageLanguageEnabled(value = import.meta.env?.VITE_SIMULATION_MESSAGE_LANGUAGE) {
  return value !== 'false'
}

function renderTemplate(template, location, locationKannada) {
  return template.replaceAll('{location}', location).replaceAll('{location_kn}', locationKannada)
}

export function buildSimulationMessage(location, risk, language = 'en') {
  const place = String(location || '')
  const level = String(risk || '').toUpperCase()
  const englishRisk = SIMULATION_MESSAGE_TEMPLATES.en[level] ? level : 'HIGH'
  const kannadaRisk = SIMULATION_MESSAGE_TEMPLATES.kn[level] ? level : 'HIGH'
  const english = renderTemplate(SIMULATION_MESSAGE_TEMPLATES.en[englishRisk], place, '')
  if (language === 'en') return english

  const locationKannada = SIMULATION_MESSAGE_LOCATIONS_KN[place] || place
  const kannada = renderTemplate(SIMULATION_MESSAGE_TEMPLATES.kn[kannadaRisk], place, locationKannada)
  return language === 'both' ? `${english}\n${kannada}` : kannada
}

export function estimateSmsSegments(message) {
  const text = String(message || '')
  let gsm7Units = 0
  let isGsm7 = true
  for (const character of text) {
    if (GSM7_BASIC.has(character)) gsm7Units += 1
    else if (GSM7_EXTENSION.has(character)) gsm7Units += 2
    else {
      isGsm7 = false
      break
    }
  }
  const encoding = isGsm7 ? 'GSM-7' : 'Unicode'
  const units = isGsm7 ? gsm7Units : text.length
  const singleSegmentLimit = isGsm7 ? 160 : 70
  const splitSegmentLimit = isGsm7 ? 153 : 67
  const segments = units === 0 ? 0 : units <= singleSegmentLimit ? 1 : Math.ceil(units / splitSegmentLimit)
  return { characters: text.length, encoding, units, singleSegmentLimit, splitSegmentLimit, segments }
}
