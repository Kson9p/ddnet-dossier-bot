import { el } from '../utils/dom.js';
import { button } from './components.js';
import { trapFocus } from './focusTrap.js';
import { lockScroll, unlockScroll } from './scrollLock.js';
import { clearActiveOverlay, hasActiveOverlay, setActiveOverlay } from './overlayRegistry.js';

/** @param {string} message @returns {Promise<boolean>} */
export function confirmDialog(message) {
  if (hasActiveOverlay()) return Promise.resolve(false);

  return new Promise((resolve) => {
    const app = document.getElementById('app');
    const overlayRoot = document.getElementById('overlay-root');
    if (!overlayRoot) {
      resolve(false);
      return;
    }

    const previouslyFocused = document.activeElement;
    let closed = false;
    let releaseTrap = null;

    const close = (accepted = false) => {
      if (closed) return;
      closed = true;
      clearActiveOverlay(close);
      document.removeEventListener('keydown', onKeyDown);
      releaseTrap?.();
      if (app) app.inert = false;
      unlockScroll();
      overlay.classList.add('is-closing');
      window.setTimeout(() => {
        overlay.remove();
        if (previouslyFocused instanceof HTMLElement) previouslyFocused.focus();
      }, 150);
      resolve(accepted);
    };

    function onKeyDown(event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        close(false);
      }
    }

    const dialog = el('section', {
      class: 'site-confirm',
      attrs: {
        role: 'alertdialog',
        'aria-modal': 'true',
        'aria-labelledby': 'site-confirm-title',
        'aria-describedby': 'site-confirm-message',
        tabindex: '-1',
      },
    }, [
      el('h2', { class: 'site-confirm__title', id: 'site-confirm-title', text: 'Подтвердить оценку' }),
      el('p', { class: 'site-confirm__message', id: 'site-confirm-message', text: message }),
      el('div', { class: 'site-confirm__actions' }, [
        button({ label: 'Отмена', variant: 'secondary', onClick: () => close(false) }),
        button({ label: 'ОК', variant: 'primary', onClick: () => close(true) }),
      ]),
    ]);
    const overlay = el('div', { class: 'overlay overlay--confirm' }, [
      el('div', { class: 'overlay__backdrop', on: { click: () => close(false) } }),
      dialog,
    ]);

    lockScroll();
    if (app) app.inert = true;
    overlayRoot.appendChild(overlay);
    document.addEventListener('keydown', onKeyDown);
    releaseTrap = trapFocus(dialog);
    setActiveOverlay(close);
    void overlay.offsetWidth;
    overlay.classList.add('is-open');
    dialog.querySelector('.btn--primary')?.focus();
  });
}
