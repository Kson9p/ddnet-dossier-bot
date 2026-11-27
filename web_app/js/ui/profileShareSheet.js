import { copyText, el } from '../utils/dom.js';
import { button, iconButton } from './components.js';
import { trapFocus } from './focusTrap.js';
import { lockScroll, unlockScroll } from './scrollLock.js';
import { clearActiveOverlay, hasActiveOverlay, setActiveOverlay } from './overlayRegistry.js';
import { showToast } from './toast.js';
import { telegram } from '../telegram.js';

/** @param {{id: string, nick: string}} player */
export function openProfileShareSheet(player) {
  if (hasActiveOverlay()) return;

  // Do not include Telegram's signed init-data query parameters in shared links.
  const url = new URL(window.location.origin + window.location.pathname);
  url.hash = `#/player/${encodeURIComponent(player.id)}`;
  const profileUrl = url.toString();
  const shareText = `${player.nick} — анкета игрока DDNet.`;
  const previouslyFocused = document.activeElement;
  const app = document.getElementById('app');
  lockScroll();
  if (app) app.inert = true;

  let closed = false;
  let releaseTrap = null;

  const close = () => {
    if (closed) return;
    closed = true;
    clearActiveOverlay(close);
    document.removeEventListener('keydown', onKeyDown);
    releaseTrap?.();
    overlay.classList.add('is-closing');
    if (app) app.inert = false;
    unlockScroll();
    window.setTimeout(() => {
      overlay.remove();
      if (previouslyFocused instanceof HTMLElement) previouslyFocused.focus();
    }, 180);
  };

  function onKeyDown(event) {
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
    }
  }

  async function copyProfileLink() {
    const copied = await copyText(profileUrl);
    showToast(copied ? 'Ссылка на анкету скопирована' : 'Не удалось скопировать ссылку', {
      iconName: copied ? 'check' : 'alert',
      tone: copied ? 'default' : 'danger',
    });
  }

  function shareTelegram() {
    const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(profileUrl)}&text=${encodeURIComponent(shareText)}`;
    close();
    telegram.openTelegramLink(shareUrl);
  }

  async function shareOtherApps() {
    if (!navigator.share) {
      await copyProfileLink();
      return;
    }
    try {
      await navigator.share({ title: `${player.nick} · DDNet`, text: shareText, url: profileUrl });
      close();
    } catch (error) {
      if (error?.name !== 'AbortError') {
        showToast('Не удалось открыть меню приложений', { iconName: 'alert', tone: 'danger' });
      }
    }
  }

  const linkField = el('input', {
    class: 'share-sheet__url',
    type: 'text',
    value: profileUrl,
    attrs: { readonly: true, 'aria-label': 'Ссылка на анкету' },
    on: { focus: (event) => event.currentTarget.select() },
  });
  const sheet = el('section', {
    class: 'sheet share-sheet',
    attrs: {
      role: 'dialog',
      'aria-modal': 'true',
      'aria-labelledby': 'share-title',
      tabindex: '-1',
    },
  }, [
    el('span', { class: 'sheet__handle', attrs: { 'aria-hidden': 'true' } }),
    el('div', { class: 'sheet__head' }, [
      el('div', {}, [
        el('p', { class: 'sheet__eyebrow', text: player.nick }),
        el('h2', { class: 'sheet__title', id: 'share-title', text: 'Поделиться анкетой' }),
      ]),
      iconButton({ iconName: 'x', label: 'Закрыть', onClick: close }),
    ]),
    el('div', { class: 'sheet__body share-sheet__body' }, [
      el('p', { class: 'sheet__lead', text: 'Скопируй ссылку или отправь анкету через приложение.' }),
      el('div', { class: 'share-sheet__link-row' }, [
        linkField,
        button({ label: 'Копировать', variant: 'secondary', iconName: 'copy', onClick: copyProfileLink }),
      ]),
      el('div', { class: 'share-sheet__destinations' }, [
        button({ label: 'Telegram', variant: 'primary', iconName: 'share', onClick: shareTelegram }),
        button({ label: 'Другие приложения', variant: 'secondary', iconName: 'external', onClick: shareOtherApps }),
      ]),
      el('p', { class: 'share-sheet__hint', text: '«Другие приложения» откроет меню доступных на устройстве способов отправки.' }),
    ]),
    el('div', { class: 'sheet__footer share-sheet__footer' }, [
      button({ label: 'Закрыть', variant: 'secondary', onClick: close }),
    ]),
  ]);
  const overlay = el('div', { class: 'overlay overlay--sheet' }, [
    el('div', { class: 'overlay__backdrop', on: { click: close } }),
    sheet,
  ]);

  document.getElementById('overlay-root')?.appendChild(overlay);
  document.addEventListener('keydown', onKeyDown);
  releaseTrap = trapFocus(sheet);
  void overlay.offsetWidth;
  overlay.classList.add('is-open');
  sheet.focus();
  setActiveOverlay(close);
}
