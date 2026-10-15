// Advisory keyword matches only. This list is not a rights registry or clearance.
// Add specific names here rather than flagging ordinary words such as "baker".
const WATCH_TERMS: { kind: string; terms: string[] }[] = [
  { kind: 'brand name', terms: [
    'Amazon', 'Adidas', 'Disney', 'Dollar Tree', 'Etsy', 'Hobby Lobby', 'Lego',
    'Marvel', 'Nintendo', 'Nike', 'PlayStation', 'Stanley', 'Ted Baker', 'TikTok', 'Xbox',
  ] },
  { kind: 'character or entertainment name', terms: [
    'Barbie', 'Bluey', 'Fortnite', 'Harry Potter', 'Hello Kitty', 'Mickey Mouse',
    'Minecraft', 'Pokémon', 'Snoopy', 'Spider-Man', 'Star Wars',
  ] },
  { kind: 'public figure or fan name', terms: [
    'Baker Mayfield', 'Taylor Swift', 'Swiftie',
  ] },
  { kind: 'sports league name', terms: ['MLB', 'NBA', 'NFL', 'NHL'] },
  { kind: 'possible reference to someone else’s work', terms: [
    'Fan art', 'Fanart', 'Inspired by', 'Replica', 'Lookalike',
  ] },
]

export interface KeywordRightsMatch {
  term: string
  kind: string
}

function normalize(value: string): string {
  return value.normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase()
    .replace(/[’']/g, '').replace(/[^a-z0-9]+/g, ' ').trim()
}

const WATCH_LIST = WATCH_TERMS.flatMap(({ kind, terms }) => terms.map(term => ({
  term, kind, normalized: normalize(term),
})))

export function keywordRightsMatches(keyword: string): KeywordRightsMatch[] {
  const words = ` ${normalize(keyword)} `
  return WATCH_LIST.filter(match => words.includes(` ${match.normalized} `)
    || words.includes(` ${match.normalized}s `))
    .map(({ term, kind }) => ({ term, kind }))
}
