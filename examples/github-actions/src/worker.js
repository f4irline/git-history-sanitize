export function reconciliationSummary(batch) {
  return { settlementId: batch.settlementId, status: 'accepted' }
}
