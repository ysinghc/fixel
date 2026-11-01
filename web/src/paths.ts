/** Every page has a URL. Finding keys contain | # : and /, so they are always percent-encoded in a path segment. */
export const paths = {
  home: '/',
  scan: '/scan',
  runs: '/runs',
  run: (run: string) => `/runs/${run}`,
  screens: (run: string) => `/runs/${run}/screens`,
  screen: (run: string, state: string) => `/runs/${run}/screens/${encodeURIComponent(state)}`,
  finding: (run: string, key: string) => `/runs/${run}/findings/${encodeURIComponent(key)}`,
  fix: (run: string, fix: string) => `/runs/${run}/fixes/${fix}`,
  label: '/label',
  benchmark: '/benchmark',
}
