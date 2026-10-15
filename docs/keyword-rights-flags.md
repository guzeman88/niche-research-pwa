# Advisory keyword rights flags

The Keywords page (desktop table and mobile cards), supported-keyword candidates,
and product-preparation form show **Possible rights issue** for recognized names
and fan-work phrases. Expand the flag with a click, Enter or Space to see what
matched and why. Keywords remain visible and product preparation stays available.

This is a small local keyword watchlist, not a registry lookup or legal decision.
Matches can be false positives and unknown names can be missed. No flag does not
mean clearance. The wording covers possible copyright, trademark and personal-name
issues without claiming that a matched name is copyrighted or that a use infringes.

Maintain specific names and phrases in `src/lib/keywordRights.ts`. Matching ignores
case, accents and punctuation, handles ordinary plurals/possessives, and uses whole
words to avoid matches inside unrelated words. Avoid broad profession/first-name
rules. The list includes the previously missed Ted Baker and Baker Mayfield phrases.

The flag runs in the browser for existing and imported keyword data. It adds no
database columns, provider requests, collection jobs, qualification changes,
approval gates or marketplace actions. Existing independent review checks remain.

Run `npm test`, `npm run lint`, `npm run build` and, against Vite preview,
`node scripts/test-keyword-rights-ui.mjs`. The browser check uses only fixtures and
is also part of `npm run test:ui`.
