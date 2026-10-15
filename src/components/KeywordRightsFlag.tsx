import { keywordRightsMatches } from '../lib/keywordRights'

export default function KeywordRightsFlag({ keyword }: { keyword: string }) {
  const matches = keywordRightsMatches(keyword)
  if (!matches.length) return null

  return <details className="mt-2 max-w-sm whitespace-normal text-left text-xs font-normal">
    <summary className="w-fit cursor-pointer rounded-sm py-1 font-semibold text-accent-amber focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-200">
      Possible rights issue
    </summary>
    <div className="mt-2 space-y-2 leading-relaxed text-surface-200">
      <ul className="list-disc space-y-1 pl-4">
        {matches.map(match => <li key={match.term}>“{match.term}” · {match.kind}</li>)}
      </ul>
      <p>This may involve copyright, trademark or a person’s identity. Review the intended use before creating a product or listing.</p>
      <p>Known-term matches only; no registry lookup. A missing flag is not legal clearance. This flag does not block your work.</p>
    </div>
  </details>
}
