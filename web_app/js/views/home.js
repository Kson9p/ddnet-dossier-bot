import { playersApi } from '../api/playersApi.js';
import { API_ERROR_TEXT } from '../api/errors.js';
import { config } from '../config.js';
import { telegram } from '../telegram.js';
import { el, debounce } from '../utils/dom.js';
import { plural } from '../utils/format.js';
import { openAboutSheet } from '../ui/aboutSheet.js';
import { showToast } from '../ui/toast.js';
import {
  appHeader,
  button,
  demoNotice,
  playerCard,
  skeletonList,
  stateView,
} from '../ui/components.js';
import { icon } from '../ui/icons.js';

const SORTS = [
  { id: 'default', label: 'Все' },
  { id: 'points', label: 'По очкам' },
];

/**
 * Главная страница: поиск и список одобренных анкет.
 * @param {{ root: HTMLElement, signal: AbortSignal, scrollY?: number }} context
 */
export function renderHome({ root, signal, scrollY = 0 }) {
  let query = '';
  let sort = 'default';
  let page = 1;
  let items = [];
  let total = 0;
  let hasMore = false;
  let loading = false;
  let loadingMore = false;
  let requestId = 0;
  let pendingScroll = scrollY;

  const countPill = el('span', { class: 'section-count', text: '…' });
  const sectionLabel = el('span', { text: 'Загрузка' });
  const listHost = el('div', { class: 'list-host', attrs: { 'aria-busy': 'true' } });

  const searchInput = el('input', {
    class: 'search__input',
    type: 'text',
    inputMode: 'search',
    enterKeyHint: 'search',
    placeholder: 'Поиск по нику',
    autocomplete: 'off',
    spellcheck: false,
    attrs: { 'aria-label': 'Поиск анкет по нику' },
  });

  const clearButton = el(
    'button',
    {
      class: 'search__clear',
      type: 'button',
      hidden: true,
      attrs: { 'aria-label': 'Очистить поиск' },
      on: { click: () => resetSearch() },
    },
    icon('x', { size: 16 }),
  );

  const searchBox = el('div', { class: 'search' }, [
    el('span', { class: 'search__icon' }, icon('search', { size: 19 })),
    searchInput,
    clearButton,
  ]);

  const chipButtons = SORTS.map((option) =>
    el(
      'button',
      {
        class: `chip${option.id === sort ? ' is-active' : ''}`,
        type: 'button',
        attrs: { 'aria-pressed': String(option.id === sort) },
        dataset: { sort: option.id },
        on: {
          click: () => {
            if (sort === option.id) return;
            sort = option.id;
            telegram.haptic('light');
            for (const chip of chipButtons) {
              const active = chip.dataset.sort === sort;
              chip.classList.toggle('is-active', active);
              chip.setAttribute('aria-pressed', String(active));
            }
            load({ reset: true });
          },
        },
      },
      option.label,
    ),
  );

  const view = el('div', { class: 'view view--home' }, [
    appHeader({
      title: 'Анкеты DDNet',
      subtitle: 'Демо-каталог игроков',
      logo: true,
      titleTag: 'h1',
      actions: [
        { iconName: 'info', label: 'О демо-версии', onClick: () => openAboutSheet() },
      ],
    }),
    el('main', { class: 'home' }, [
      el('div', { class: 'home__top' }, [
        searchBox,
        el('div', {
          class: 'chips',
          attrs: { role: 'group', 'aria-label': 'Сортировка анкет' },
        }, chipButtons),
      ]),
      el('div', { class: 'home__list' }, [
        el('div', { class: 'section-head' }, [
          el('h2', { class: 'section-title' }, [sectionLabel, countPill]),
          el('span', { class: 'section-hint', text: 'только одобренные' }),
        ]),
        listHost,
      ]),
      el('footer', { class: 'home__footer' }, [
        demoNotice(),
        el(
          'button',
          {
            class: 'link-button',
            type: 'button',
            on: { click: () => openAboutSheet() },
          },
          'Как устроена демо-версия',
        ),
      ]),
    ]),
  ]);

  root.replaceChildren(view);

  const runSearch = debounce((value) => {
    const next = value.trim();
    if (next === query) return;
    query = next;
    load({ reset: true });
  }, 260);

  searchInput.addEventListener('input', () => {
    clearButton.hidden = searchInput.value.length === 0;
    if (searchInput.value.length === 0) {
      runSearch.cancel();
      if (query !== '') {
        query = '';
        load({ reset: true });
      }
      return;
    }
    runSearch(searchInput.value);
  });

  searchInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      runSearch.cancel();
      const next = searchInput.value.trim();
      if (next !== query) {
        query = next;
        load({ reset: true });
      }
      searchInput.blur();
    }
  });

  function resetSearch() {
    searchInput.value = '';
    clearButton.hidden = true;
    query = '';
    runSearch.cancel();
    load({ reset: true });
    searchInput.focus();
  }

  function renderSkeletons() {
    sectionLabel.textContent = 'Загрузка';
    countPill.textContent = '…';
    countPill.hidden = false;
    listHost.setAttribute('aria-busy', 'true');
    listHost.replaceChildren(skeletonList(3));
  }

  function renderError(error) {
    sectionLabel.textContent = 'Ошибка';
    countPill.hidden = true;
    listHost.removeAttribute('aria-busy');
    listHost.replaceChildren(
      stateView({
        iconName: 'alert',
        title: 'Не удалось загрузить анкеты',
        text: API_ERROR_TEXT[error?.code] ?? API_ERROR_TEXT.server,
        tone: 'danger',
        actions: [
          button({
            label: 'Повторить',
            variant: 'secondary',
            iconName: 'refresh',
            onClick: () => load({ reset: true }),
          }),
        ],
      }),
    );
  }

  function renderResults() {
    sectionLabel.textContent = query ? 'Результаты' : 'Игроки';
    countPill.hidden = false;
    countPill.textContent = String(total);
    listHost.removeAttribute('aria-busy');

    if (items.length === 0) {
      const text = query
        ? `По запросу «${query}» ничего не нашлось. Попробуйте другой ник или сбросьте поиск.`
        : 'В каталоге пока нет одобренных анкет.';
      listHost.replaceChildren(
        stateView({
          iconName: 'search',
          title: 'Ничего не найдено',
          text,
          actions: query
            ? [
                button({
                  label: 'Сбросить поиск',
                  variant: 'secondary',
                  onClick: resetSearch,
                }),
              ]
            : [],
        }),
      );
      return;
    }

    const list = el(
      'div',
      { class: 'player-list' },
      items.map((player) => playerCard(player)),
    );

    const remaining = Math.max(0, total - items.length);
    const loadMore =
      hasMore && remaining > 0
        ? el(
            'button',
            {
              class: 'btn btn--secondary btn--block load-more',
              type: 'button',
              on: { click: () => load({ reset: false }) },
            },
            [
              el('span', {
                text: `Показать ещё ${remaining} ${plural(remaining, ['анкету', 'анкеты', 'анкет'])}`,
              }),
            ],
          )
        : null;

    listHost.replaceChildren(list, loadMore ?? '');
  }

  async function load({ reset = false } = {}) {
    if (!reset && (loading || loadingMore)) return;

    const currentRequest = ++requestId;
    const requestedPage = reset ? 1 : page + 1;

    if (reset) {
      loading = true;
      loadingMore = false;
      page = 1;
      renderSkeletons();
    } else {
      loadingMore = true;
      const more = listHost.querySelector('.load-more');
      if (more) {
        more.disabled = true;
        more.textContent = 'Загрузка…';
      }
    }

    try {
      const result = await playersApi.getPlayers({
        query,
        sort,
        page: requestedPage,
        pageSize: config.pageSize,
        signal,
      });

      if (signal.aborted || currentRequest !== requestId) return;

      items = reset ? result.items : items.concat(result.items);
      total = result.total;
      hasMore = result.hasMore;
      page = requestedPage;
      loading = false;
      loadingMore = false;
      renderResults();

      if (pendingScroll > 0) {
        const target = pendingScroll;
        pendingScroll = 0;
        requestAnimationFrame(() => window.scrollTo(0, target));
      }
    } catch (error) {
      if (signal.aborted || error?.name === 'AbortError' || currentRequest !== requestId) {
        return;
      }

      loading = false;
      loadingMore = false;

      if (reset) {
        renderError(error);
      } else {
        renderResults();
        showToast('Не удалось загрузить ещё анкеты', {
          iconName: 'alert',
          tone: 'danger',
        });
      }
    }
  }

  load({ reset: true });

  return () => {
    runSearch.cancel();
  };
}
