/** Optional text translations and Intl formatting. Text is never rendered as HTML. */
/** @typedef {string | Record<string,string>} Message */
/** @typedef {{locale?:string,fallback?:string,messages?:Record<string,Record<string,Message>>}} I18nOptions */
/** @param {I18nOptions} [options] */
export function createI18n(options = {}) {
  let locale = options.locale || 'en';
  const messages = options.messages || {};
  const fallback = options.fallback || 'en';
  /** @type {Set<()=>void>} */ const listeners = new Set();
  const api = {
    get locale() { return locale; },
    /** @param {string} next */ setLocale(next) { new Intl.PluralRules(next); locale = next; for (const listener of listeners) listener(); },
    /** @param {string} key @param {Record<string,string|number>} [params] */
    t(key, params = {}) {
      let message = messages[locale]?.[key] ?? messages[fallback]?.[key] ?? key;
      if (typeof message === 'object') {
        const count = Number(params.count ?? 0);
        message = message[new Intl.PluralRules(locale).select(count)] ?? message.other ?? key;
      }
      return message.replace(/\{(\w+)\}/g, (match, name) => Object.hasOwn(params,name) ? String(params[name]) : match);
    },
    /** @param {number} value @param {Intl.NumberFormatOptions} [format] */ number(value, format) { return new Intl.NumberFormat(locale,format).format(value); },
    /** @param {Date|number} value @param {Intl.DateTimeFormatOptions} [format] */ date(value, format) { return new Intl.DateTimeFormat(locale,format).format(value); },
    /** @param {()=>void} listener */ subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
  };
  return api;
}
