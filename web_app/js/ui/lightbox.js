import { el } from '../utils/dom.js';
import { trapFocus } from './focusTrap.js';
import { icon } from './icons.js';
import { lockScroll, unlockScroll } from './scrollLock.js';
import { clearActiveOverlay, setActiveOverlay } from './overlayRegistry.js';
import { showToast } from './toast.js';

let activeClose = null;

/**
 * Полноэкранная галерея с листанием.
 * @param {import('../api/types.js').GalleryItem[]} items
 * @param {number} [startIndex]
 */
export function openLightbox(items, startIndex = 0) {
  if (activeClose) return;

  const media = items.filter((item) =>
    item.type === 'image' ? Boolean(item.src) : Boolean(item.poster),
  );
  if (media.length === 0) return;

  let index = Math.min(Math.max(0, startIndex), media.length - 1);
  const previouslyFocused = document.activeElement;
  const app = document.getElementById('app');
  let closed = false;
  let releaseTrap = null;

  lockScroll();
  if (app) app.inert = true;

  const counter = el('span', { class: 'lightbox__counter' });
  const stage = el('div', { class: 'lightbox__stage' });
  const caption = el('p', { class: 'lightbox__caption' });
  const meta = el('span', { class: 'lightbox__meta' });

  const prevButton = el(
    'button',
    {
      class: 'lightbox__nav lightbox__nav--prev',
      type: 'button',
      attrs: { 'aria-label': 'Предыдущий материал' },
      on: { click: () => go(-1) },
    },
    icon('chevronLeft', { size: 24 }),
  );

  const nextButton = el(
    'button',
    {
      class: 'lightbox__nav lightbox__nav--next',
      type: 'button',
      attrs: { 'aria-label': 'Следующий материал' },
      on: { click: () => go(1) },
    },
    icon('chevronRight', { size: 24 }),
  );

  function renderMedia() {
    const item = media[index];
    counter.textContent = `${index + 1} / ${media.length}`;
    caption.textContent = item.caption || 'Без подписи';
    meta.textContent =
      item.type === 'video' ? `Видео${item.duration ? ` · ${item.duration}` : ''}` : 'Фото';

    const content =
      item.type === 'video'
        ? el('div', { class: 'lightbox__video' }, [
            el('img', {
              class: 'lightbox__image',
              src: item.poster,
              alt: item.caption || 'Постер демонстрационного видео',
              draggable: false,
            }),
            el(
              'button',
              {
                class: 'lightbox__play',
                type: 'button',
                attrs: { 'aria-label': 'Воспроизвести демонстрационное видео' },
                on: {
                  click: () =>
                    showToast('В демо-версии видео недоступно: это заглушка', {
                      iconName: 'video',
                    }),
                },
              },
              [icon('play', { size: 30 }), el('span', { text: 'Демо-видео' })],
            ),
          ])
        : el('img', {
            class: 'lightbox__image',
            src: item.src,
            alt: item.caption || 'Демонстрационное изображение',
            draggable: false,
          });

    stage.replaceChildren(content);
    prevButton.disabled = index === 0;
    nextButton.disabled = index === media.length - 1;

    const next = media[index + 1];
    if (next?.type === 'image' && next.src) new Image().src = next.src;
    const prev = media[index - 1];
    if (prev?.type === 'image' && prev.src) new Image().src = prev.src;
  }

  /** @param {number} delta */
  function go(delta) {
    const next = index + delta;
    if (next < 0 || next >= media.length) return;
    index = next;
    renderMedia();
  }

  function close() {
    if (closed) return;
    closed = true;
    activeClose = null;
    clearActiveOverlay(close);
    document.removeEventListener('keydown', onKeyDown);
    releaseTrap?.();
    overlay.classList.add('is-closing');
    if (app) app.inert = false;
    unlockScroll();
    window.setTimeout(() => {
      overlay.remove();
      if (previouslyFocused instanceof HTMLElement) previouslyFocused.focus();
    }, 160);
  }

  function onKeyDown(event) {
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault();
      go(-1);
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      go(1);
    }
  }

  const closeButton = el(
    'button',
    {
      class: 'lightbox__close',
      type: 'button',
      attrs: { 'aria-label': 'Закрыть галерею' },
      on: { click: close },
    },
    icon('x', { size: 22 }),
  );

  const dialog = el(
    'div',
    {
      class: 'lightbox',
      attrs: {
        role: 'dialog',
        'aria-modal': 'true',
        'aria-label': 'Галерея анкеты',
        tabindex: '-1',
      },
    },
    [
      el('header', { class: 'lightbox__head' }, [
        el('div', { class: 'lightbox__head-text' }, [
          el('span', { class: 'lightbox__title', text: 'Галерея' }),
          counter,
        ]),
        closeButton,
      ]),
      el('div', { class: 'lightbox__viewport' }, [prevButton, stage, nextButton]),
      el('footer', { class: 'lightbox__foot' }, [
        caption,
        meta,
      ]),
    ],
  );

  const overlay = el('div', { class: 'overlay overlay--lightbox' }, [dialog]);

  overlay.addEventListener('click', (event) => {
    if (event.target === overlay) close();
  });

  // Свайпы по горизонтали.
  let startX = 0;
  let startY = 0;
  let tracking = false;

  stage.addEventListener(
    'touchstart',
    (event) => {
      const touch = event.changedTouches[0];
      startX = touch.clientX;
      startY = touch.clientY;
      tracking = true;
    },
    { passive: true },
  );

  stage.addEventListener(
    'touchend',
    (event) => {
      if (!tracking) return;
      tracking = false;
      const touch = event.changedTouches[0];
      const dx = touch.clientX - startX;
      const dy = touch.clientY - startY;
      if (Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.4) {
        go(dx < 0 ? 1 : -1);
      }
    },
    { passive: true },
  );

  document.getElementById('overlay-root')?.appendChild(overlay);
  document.addEventListener('keydown', onKeyDown);
  releaseTrap = trapFocus(dialog);
  activeClose = close;

  renderMedia();

  void overlay.offsetWidth;
  overlay.classList.add('is-open');
  dialog.focus();
  setActiveOverlay(close);
}
