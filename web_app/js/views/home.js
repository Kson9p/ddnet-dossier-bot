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
    if (id === 'all') return gender === '';
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
            } else {
              gender = option.id;
            }
            updateFilterControls();
            telegram.haptic('light');
            load({ reset: true });
          },
        },
      },
      option.label,
    ),
  );

  const filtersScroller = el('div', {
    class: 'chips',
    attrs: { role: 'group', 'aria-label': 'Фильтры анкет' },
    on: {
      wheel: (event) => {
        const scroller = event.currentTarget;
        if (Math.abs(event.deltaY) > Math.abs(event.deltaX)) {
          const maxScroll = scroller.scrollWidth - scroller.clientWidth;
          const nextScroll = Math.max(0, Math.min(maxScroll, scroller.scrollLeft + event.deltaY));
          if (nextScroll !== scroller.scrollLeft) {
            scroller.scrollLeft = nextScroll;
            event.preventDefault();
          }
        }
      },
    },
  }, chipButtons);

  const SORT_OPTIONS = [
    { value: 'default', label: 'Сортировка' },
    { value: 'rating_desc', label: 'Рейтинг: выше' },
    { value: 'rating_asc', label: 'Рейтинг: ниже' },
    { value: 'name_asc', label: 'Имя: A–Z' },
    { value: 'name_desc', label: 'Имя: Z–A' },
  ];
  let sortMenuOpen = false;
  const sortMenuButtons = SORT_OPTIONS.map((option) =>
    el('button', {
      class: 'sort-menu__option',
      type: 'button',
      attrs: { role: 'menuitemradio', 'aria-checked': String(sort === option.value) },
      on: {
        click: () => {
          sort = option.value;
          sortMenuOpen = false;
          sortMenu.hidden = true;
          sortButton.setAttribute('aria-expanded', 'false');
          updateFilterControls();
          telegram.haptic('light');
          load({ reset: true });
        },
      },
    }, [
      el('span', { text: option.label }),
      el('span', { class: 'sort-menu__check', attrs: { 'aria-hidden': 'true' }, text: '✓' }),
    ]),
  );
  const sortMenu = el('div', {
    class: 'sort-menu',
    attrs: { role: 'menu', 'aria-label': 'Сортировка анкет', hidden: true },
  }, sortMenuButtons);
  const sortButton = el('button', {
    class: 'sort-control',
    type: 'button',
    attrs: { 'aria-label': 'Сортировка анкет', 'aria-haspopup': 'menu', 'aria-expanded': 'false', title: 'Сортировка анкет' },
    on: {
      click: () => {
        sortMenuOpen = !sortMenuOpen;
        sortMenu.hidden = !sortMenuOpen;
        sortButton.setAttribute('aria-expanded', String(sortMenuOpen));
      },
    },
  }, icon('sort', { size: 18 }));
  const sortWrap = el('div', { class: 'sort-wrap' }, [sortButton, sortMenu]);
  const scrollTrack = el('div', {
    class: 'chips-scrollbar',
    attrs: { 'aria-hidden': 'true' },
  }, el('span', { class: 'chips-scrollbar__thumb' }));
  const scrollThumb = scrollTrack.firstElementChild;

  function updateScrollIndicator() {
    const maxScroll = filtersScroller.scrollWidth - filtersScroller.clientWidth;
    if (maxScroll <= 1) {
      scrollTrack.hidden = true;
      return;
    }
    scrollTrack.hidden = false;
    const visibleWidth = Math.max(20, filtersScroller.clientWidth ** 2 / filtersScroller.scrollWidth);
    const thumbTravel = filtersScroller.clientWidth - visibleWidth;
    const thumbOffset = maxScroll > 0 ? filtersScroller.scrollLeft / maxScroll * thumbTravel : 0;
    scrollThumb.style.width = `${visibleWidth}px`;
    scrollThumb.style.transform = `translateX(${thumbOffset}px)`;
  }

  function updateFilterControls() {
    for (const chip of chipButtons) {
      const active = chipIsActive(chip.dataset.filter);
      chip.classList.toggle('is-active', active);
      chip.setAttribute('aria-pressed', String(active));
    }
    sortMenuButtons.forEach((menuButton, index) => {
      const active = SORT_OPTIONS[index].value === sort;
      menuButton.classList.toggle('is-active', active);
      menuButton.setAttribute('aria-checked', String(active));
    });
  }

  updateFilterControls();

  function closeSortMenu(event) {
    if (event?.type === 'keydown' && event.key !== 'Escape') return;
    if (event?.type === 'pointerdown' && sortWrap.contains(event.target)) return;
    if (!sortMenuOpen) return;
    sortMenuOpen = false;
    sortMenu.hidden = true;
    sortButton.setAttribute('aria-expanded', 'false');
  }


  const view = el('div', { class: 'view view--home' }, [
    el('main', { class: 'home' }, [
      el('div', { class: 'home__top' }, [
        searchBox,
        el('div', { class: 'filter-row' }, [
          el('div', { class: 'chips-wrap' }, [filtersScroller, scrollTrack]),
          sortWrap,
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
  filtersScroller.addEventListener('scroll', updateScrollIndicator, { passive: true });
  document.addEventListener('pointerdown', closeSortMenu);
  document.addEventListener('keydown', closeSortMenu);
  const scrollObserver = new ResizeObserver(updateScrollIndicator);
  scrollObserver.observe(filtersScroller);
  updateScrollIndicator();

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
    scrollObserver.disconnect();
    filtersScroller.removeEventListener('scroll', updateScrollIndicator);
    document.removeEventListener('pointerdown', closeSortMenu);
    document.removeEventListener('keydown', closeSortMenu);
  };
}
