/** Optional document metadata management; only plugin-owned tags are removed. */
/** @typedef {{title?:string,description?:string,canonical?:string,ogTitle?:string,ogDescription?:string,ogImage?:string, "og:title"?:string, "og:description"?:string, "og:image"?:string}} HeadOptions */
/** @param {HeadOptions} [defaults] */
export function createHead(defaults = {}) {
  const originalTitle = document.title;
  /** @type {Element[]} */ const owned = Array.from(document.querySelectorAll('[data-teloce-head]'));
  /** @param {string} value */ const url = value => {
    const parsed = new URL(value, location.href);
    if (!['http:','https:'].includes(parsed.protocol)) throw new Error('Metadata URLs must use HTTP or HTTPS');
    return parsed.href;
  };
  const clear = () => { for (const element of owned.splice(0)) element.remove(); };
  /** @param {HeadOptions} [page] */
  const set = (page = {}) => {
    const next = {...defaults,...page};
    // Validate before mutating existing metadata.
    const canonical = next.canonical ? url(next.canonical) : '';
    const image = (next.ogImage || next['og:image']) ? url(next.ogImage || next['og:image'] || '') : '';
    clear(); document.title = next.title ?? originalTitle;
    for (const [key,value] of Object.entries({description:next.description,'og:title':next.ogTitle ?? next['og:title'],'og:description':next.ogDescription ?? next['og:description'],'og:image':image})) {
      if (!value) continue;
      const tag = document.createElement('meta');
      tag.setAttribute(key.startsWith('og:') ? 'property' : 'name', key);
      tag.setAttribute('content',value); tag.setAttribute('data-teloce-head',''); document.head.append(tag); owned.push(tag);
    }
    if (canonical) { const tag = document.createElement('link'); tag.rel = 'canonical'; tag.href = canonical; tag.setAttribute('data-teloce-head',''); document.head.append(tag); owned.push(tag); }
  };
  set();
  return {set, destroy() { clear(); document.title = originalTitle; }};
}
