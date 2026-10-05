export function scenarioKey(location, risk) {
  return `${location}:${risk}`
}

export function simulationExcelFilename(selections) {
  if (selections.length === 1) {
    return `LANDsense_SIMULATION_${selections[0].location}_${selections[0].risk}_httpSMS.xlsx`
  }
  return 'LANDsense_SIMULATION_httpSMS.xlsx'
}

export function activeAdminActor(scenario, location, risk, active) {
  const actor = scenario?.adminActor
  return active && scenario.location === location && scenario.risk === risk &&
    actor?.status === 'available' && actor.is_simulation === true ? actor : null
}

export function toggleRecipient(ids, identifier, checked, people) {
  if (!people.some(person => person.displayId === identifier && person.inside && person.recipientEligible)) return ids
  return checked ? [...new Set([...ids, identifier])] : ids.filter(id => id !== identifier)
}

export function toggleDemoAdmin(ids, identifier, checked, recipients) {
  if (!recipients.some(person => person.recipientId === identifier && person.selectable)) return ids
  return checked ? [...new Set([...ids, identifier])] : ids.filter(id => id !== identifier)
}

export function exportSelections(drafts) {
  return Object.values(drafts).filter(draft => draft.selected.length || draft.demoAdmins?.length).map(draft => ({
    location: draft.scenario.location, risk: draft.scenario.risk,
    revision: draft.scenario.revision, message: draft.message,
    recipient_ids: draft.selected,
    ...(draft.demoAdmins?.length ? { demo_admin_recipient_ids: draft.demoAdmins } : {}),
  }))
}
