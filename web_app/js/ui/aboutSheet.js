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
    title: 'Примеры анкет',
    text: 'Ники, описания и статистика сейчас тестовые. Настоящие анкеты появятся после подключения базы.',
  },
  {
    iconName: 'check',
    title: 'Только одобренные',
    text: 'Список и прямая ссылка отдают лишь анкеты со статусом «одобрена». На сервере эту проверку нужно продублировать.',
  },
  {
    iconName: 'image',
    title: 'Изображения',
    text: 'Сейчас используются графические иллюстрации. Фото и видео будут загружаться из анкет после подключения сервера.',
  },
  {
    iconName: 'lock',
    title: 'Без Bot API и токенов',
    text: 'Браузер не обращается к Telegram Bot API. В проекте нет токенов, идентификаторов и личных данных.',
  },
  {
    iconName: 'refresh',
    title: 'Готово к подключению базы',
    text: 'Работа с анкетами вынесена в API-адаптер. Для перехода на сервер достаточно переключить apiMode на «http».',
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
          text: 'Каталог игроков DDNet в формате Telegram Mini App. Сейчас в нём показаны примеры анкет; реальная база игроков ещё не подключена.',
        }),
        el('div', { class: 'fact-strip' }, [
          el('span', { class: 'fact-pill' }, [el('b', { text: '10' }), ' примеров']),
          el('span', { class: 'fact-pill' }, [el('b', { text: '3' }), ' медиа']),
          el('span', { class: 'fact-pill' }, [el('b', { text: '0' }), ' реальных анкет']),
        ]),
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
        el('span', { class: 'sheet__version', text: 'Версия 0.1' }),
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
