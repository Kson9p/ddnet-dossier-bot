import { el } from '../utils/dom.js';
import { trapFocus } from './focusTrap.js';
import { icon } from './icons.js';
import { lockScroll, unlockScroll } from './scrollLock.js';
import { clearActiveOverlay, setActiveOverlay } from './overlayRegistry.js';
import { button, iconButton } from './components.js';

let activeClose = null;

const FACTS = [
  {
    iconName: 'user',
    title: 'Анкеты игроков',
    text: 'В каталоге показываются анкеты, которые пользователи подали и модератор одобрил.',
  },
  {
    iconName: 'check',
    title: 'Только одобренные',
    text: 'Каталог и страницы профилей доступны только после одобрения модератором.',
  },
  {
    iconName: 'image',
    title: 'Изображения',
    text: 'Фото и видео в одобренной анкете показываются в её галерее.',
  },
  {
    iconName: 'lock',
    title: 'Медиа через сервер',
    text: 'Файлы передаются через сервер бота; токен Telegram не попадает в браузер.',
  },
  {
    iconName: 'refresh',
    title: 'Обновление каталога',
    text: 'После одобрения анкета появляется в каталоге сайта из базы бота.',
  },
];

/** Открывает нижнюю шторку с информацией о приложении. */
export function openAboutSheet() {
  if (activeClose) return;

  const previouslyFocused = document.activeElement;
  const app = document.getElementById('app');
  lockScroll();
  if (app) app.inert = true;

  let closed = false;
  let releaseTrap = null;

  const close = () => {
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
    }, 180);
  };

  function onKeyDown(event) {
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
    }
  }

  const closeButton = iconButton({ iconName: 'x', label: 'Закрыть', onClick: close });

  const sheet = el(
    'section',
    {
      class: 'sheet',
      attrs: {
        role: 'dialog',
        'aria-modal': 'true',
        'aria-labelledby': 'about-title',
        tabindex: '-1',
      },
    },
    [
      el('span', { class: 'sheet__handle', attrs: { 'aria-hidden': 'true' } }),
      el('div', { class: 'sheet__head' }, [
        el('div', {}, [
          el('p', { class: 'sheet__eyebrow', text: 'DDNet · анкеты' }),
          el('h2', { class: 'sheet__title', id: 'about-title', text: 'О приложении' }),
        ]),
        closeButton,
      ]),
      el('div', { class: 'sheet__body' }, [
        el('p', {
          class: 'sheet__lead',
          text: 'Каталог одобренных анкет игроков DDNet.',
        }),
        el(
          'ul',
          { class: 'fact-list' },
          FACTS.map((fact) =>
            el('li', { class: 'fact' }, [
              el('span', { class: 'fact__icon' }, icon(fact.iconName, { size: 19 })),
              el('div', {}, [
                el('h3', { class: 'fact__title', text: fact.title }),
                el('p', { class: 'fact__text', text: fact.text }),
              ]),
            ]),
          ),
        ),
      ]),
      el('div', { class: 'sheet__footer' }, [
        button({ label: 'Понятно', variant: 'primary', onClick: close }),
      ]),
    ],
  );

  const overlay = el(
    'div',
    { class: 'overlay overlay--sheet' },
    [
      el('div', { class: 'overlay__backdrop', on: { click: close } }),
      sheet,
    ],
  );

  document.getElementById('overlay-root')?.appendChild(overlay);
  document.addEventListener('keydown', onKeyDown);
  releaseTrap = trapFocus(sheet);
  activeClose = close;

  void overlay.offsetWidth;
  overlay.classList.add('is-open');
  sheet.focus();
  setActiveOverlay(close);
}
