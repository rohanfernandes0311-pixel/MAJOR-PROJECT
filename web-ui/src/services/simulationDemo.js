export function isKodaguDemoActive(result) {
  return Boolean(result?.active && result?.state?.enabled && result?.state?.is_simulation)
}

export function eligibleDemoIds(recipients = []) {
  return recipients.filter((item) => item.sms_eligible).map((item) => item.display_id)
}

export function toggleDemoRecipient(selected, id, checked, recipients) {
  if (!eligibleDemoIds(recipients).includes(id)) return selected
  return checked ? [...new Set([...selected, id])] : selected.filter((value) => value !== id)
}

export function initialDemoReview(result) {
  if (!isKodaguDemoActive(result)) return { message: '', selected: [] }
  return {
    message: result.state.alert_preview?.message || '',
    selected: []
  }
}
