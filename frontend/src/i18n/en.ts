import { BUNDLES } from './bundles'
export const en: Record<string, string> = Object.assign({}, ...BUNDLES.map(b => b.en))
