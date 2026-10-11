/** Optional navigation announcements and native dialog focus ownership. */
export function createAccessibility() {
  const live = document.createElement('div');
  live.setAttribute('aria-live','polite'); live.setAttribute('aria-atomic','true');
  Object.assign(live.style,{position:'absolute',width:'1px',height:'1px',overflow:'hidden',clipPath:'inset(50%)'});
  document.body.append(live);
  /** @type {Set<()=>void>} */ const cleanups = new Set();
  return {
    /** @param {string} message */ announce(message) { live.textContent = message; },
    /** @param {HTMLElement} element */ focus(element) { if (element.tabIndex < 0 && !element.hasAttribute('tabindex')) element.tabIndex = -1; element.focus(); },
    /** Native showModal provides browser focus containment and Escape handling. @param {HTMLDialogElement} dialog */
    openDialog(dialog) {
      const previous = document.activeElement;
      dialog.showModal();
      let active = true;
      const cleanup = () => { if (!active) return; active = false; if (dialog.open) dialog.close(); dialog.removeEventListener('close',cleanup); cleanups.delete(cleanup); if (previous instanceof HTMLElement && previous.isConnected) previous.focus(); };
      cleanups.add(cleanup); dialog.addEventListener('close',cleanup,{once:true});
      return () => { if (dialog.open) dialog.close(); cleanup(); };
    },
    destroy() { for (const cleanup of [...cleanups]) cleanup(); live.remove(); },
  };
}
