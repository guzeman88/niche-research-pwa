function validateStoreIdeas(ideas) {
  if (!Array.isArray(ideas)) throw new Error('Store ideas must be an array');
  for (const idea of ideas) {
    if (!idea.id || !idea.name || !idea.keywordClusters?.length || !idea.listingBlueprints?.length
      || !Number.isFinite(idea.evidenceDepth?.score)
      || !Number.isFinite(idea.profitabilityEvidence?.evidenceScore)) {
      throw new Error(`Incomplete recommendation evidence for ${idea.name || 'unnamed store'}`);
    }
    const evidence = idea.profitabilityEvidence;
    if (idea.profitScore != null && !(evidence.observedPriceBand || evidence.sampledMonthlyRevenue
      || evidence.revenuePerListing || evidence.marketTractionScore)) {
      throw new Error(`Profit score without market evidence for ${idea.name}`);
    }
    for (const item of idea.listingBlueprints) {
      if (!item.primaryKeyword || !Array.isArray(item.supportingKeywords)
        || !item.profitInputs || !item.qualityInputs || !Number.isFinite(item.listingQualityScore)) {
        throw new Error(`Incomplete listing blueprint for ${idea.name}`);
      }
    }
  }
}
module.exports = {validateStoreIdeas};
