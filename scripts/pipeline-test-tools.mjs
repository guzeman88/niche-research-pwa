// Existing workflow regressions exercise the same forms after progressive disclosure.
// New Pipeline overview/navigation behavior has its own regression suite.
export async function openPipelineTools(page) {
  if (!['/keywords','/store-generator','/launch','/validation','/selling','/production','/stores','/evidence'].includes(new URL(page.url()).pathname)) return
  const detail = page.locator('details.pipeline-tools').first()
  await detail.waitFor()
  if (!(await detail.evaluate(el => el.open))) await detail.locator(':scope > summary').click()
  await detail.locator(':scope > .pipeline-functional').waitFor()
}
