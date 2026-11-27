import { playersApi } from '../api/playersApi.js';
import { API_ERROR_TEXT } from '../api/errors.js';
import { config } from '../config.js';
import { telegram } from '../telegram.js';
import { el, debounce } from '../utils/dom.js';
import { plural } from '../utils/format.js';
import { openAboutSheet } from '../ui/aboutSheet.js';
import { showToast } from '../ui/toast.js';
import {
  button,
  playerCard,
  skeletonList,
  stateView,
} from '../ui/components.js';
import { icon } from '../ui/icons.js';

const FILTERS = [
  { id: 'all', label: 'Все' },
  { id: 'points', label: 'По очкам' },
  { id: 'boy', label: 'Парень' },
  { id: 'girl', label: 'Девушка' },
];

/**
 * Главная страница: поиск и список одобренных анкет.
 * @param {{ root: HTMLElement, signal: AbortSignal, scrollY?: number }} context
 */
export function renderHome({ root, signal, scrollY = 0 }) {
  let query = '';
  let sort = 'default';
  let gender = '';
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

  const chipIsActive = (id) => {
    if (id === 'all') return sort !== 'points' && gender === '';
    if (id === 'points') return sort === 'points';
    return gender === id;
  };

  const chipButtons = FILTERS.map((option) =>
    el(
      'button',
      {
        class: `chip${chipIsActive(option.id) ? ' is-active' : ''}`,
        type: 'button',
        attrs: { 'aria-pressed': String(chipIsActive(option.id)) },
        dataset: { filter: option.id },
        on: {
          click: () => {
            if (option.id === 'all') {
              sort = 'default';
              gender = '';
            } else if (option.id === 'points') {
              sort = sort === 'points' ? 'default' : 'points';
            } else {
              gender = option.id;
            }
            sortSelect.value = sort;
            telegram.haptic('light');
            for (const chip of chipButtons) {
              const active = chipIsActive(chip.dataset.filter);
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


  const sortSelect = el('select', {
    class: 'sort-select',
    attrs: { 'aria-label': 'Сортировка анкет' },
    on: {
      change: (event) => {
        sort = event.currentTarget.value;
        telegram.haptic('light');
        load({ reset: true });
      },
    },
  }, [
    el('option', { value: 'default', text: 'Сортировка' }),
    el('option', { value: 'points', text: 'Очки: больше' }),
    el('option', { value: 'rating_desc', text: 'Рейтинг: выше' }),
    el('option', { value: 'rating_asc', text: 'Рейтинг: ниже' }),
    el('option', { value: 'name_asc', text: 'Имя: A–Z' }),
    el('option', { value: 'name_desc', text: 'Имя: Z–A' }),
  ]);

  const view = el('div', { class: 'view view--home' }, [
    el('main', { class: 'home' }, [
      el('div', { class: 'home__top' }, [
        searchBox,
        el('div', { class: 'filter-row' }, [
          el('div', {
            class: 'chips',
            attrs: { role: 'group', 'aria-label': 'Фильтры анкет' },
          }, chipButtons),
          el('label', { class: 'sort-control' }, [
            icon('sort', { size: 16 }),
            sortSelect,
          ]),
        ]),
      ]),
      el('div', { class: 'home__list' }, [
        el('div', { class: 'section-head' }, [
          el('h2', { class: 'section-title' }, [sectionLabel, countPill]),
          el('span', { class: 'section-hint', text: 'только одобренные' }),
        ]),
        listHost,
      ]),
      el('footer', { class: 'home__footer' }, [
        el(
          'button',
          {
            class: 'link-button',
            type: 'button',
            on: { click: () => openAboutSheet() },
          },
          'О приложении',
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
        gender,
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
