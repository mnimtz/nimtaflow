import { BUNDLES } from './bundles'
export const de: Record<string, string> = Object.assign({}, ...BUNDLES.map(b => b.de))
