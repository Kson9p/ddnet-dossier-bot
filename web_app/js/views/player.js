import { playersApi } from '../api/playersApi.js';
import { API_ERROR_TEXT } from '../api/errors.js';
import { telegram } from '../telegram.js';
import { copyText, el } from '../utils/dom.js';
import {
  formatHours,
  formatLastSeen,
  formatMaterials,
  formatNumber,
  formatRank,
} from '../utils/format.js';
import { openAboutSheet } from '../ui/aboutSheet.js';
import {
  appHeader,
  avatar,
  button,
  demoNotice,
  sectionTitle,
  stateView,
} from '../ui/components.js';
import { icon } from '../ui/icons.js';
import { openLightbox } from '../ui/lightbox.js';
import { showToast } from '../ui/toast.js';

/**
 * Подробная страница анкеты.
 * @param {{ root: HTMLElement, params: Record<string, string>, signal: AbortSignal, goBack: () => void }} context
 */
export function renderPlayer({ root, params, signal, goBack }) {
  const id = params.id ?? '';
  const content = el('div', { class: 'player-page' });

  const view = el('div', { class: 'view view--player' }, [
    appHeader({
      title: 'Анкета игрока',
      centered: true,
      onBack: goBack,
      actions: [
        { iconName: 'info', label: 'О демо-версии', onClick: () => openAboutSheet() },
      ],
    }),
    content,
  ]);

  root.replaceChildren(view);
  telegram.setBackButton(true, goBack);
  renderSkeleton();
  load();

  async function load() {
    renderSkeleton();

    try {
      const player = await playersApi.getPlayer(id, { signal });
      if (signal.aborted) return;
      renderProfile(player);
    } catch (error) {
      if (signal.aborted || error?.name === 'AbortError') return;
      renderError(error);
    }
  }

  function renderSkeleton() {
    content.replaceChildren(
      el('div', { class: 'player-skeleton', attrs: { 'aria-busy': 'true', 'aria-label': 'Загрузка анкеты' } }, [
        el('div', { class: 'skeleton skeleton--hero' }),
        el('div', { class: 'player-skeleton__head' }, [
          el('span', { class: 'skeleton skeleton--profile-avatar' }),
          el('span', { class: 'skeleton skeleton--line skeleton--w35' }),
          el('span', { class: 'skeleton skeleton--line skeleton--w55 skeleton--thin' }),
          el('span', { class: 'skeleton skeleton--line skeleton--w70 skeleton--thin' }),
        ]),
        el('div', { class: 'skeleton-tiles' }, [
          el('span', { class: 'skeleton skeleton--tile' }),
          el('span', { class: 'skeleton skeleton--tile' }),
          el('span', { class: 'skeleton skeleton--tile' }),
        ]),
        el('div', { class: 'player-skeleton__block' }, [
          el('span', { class: 'skeleton skeleton--line skeleton--w25' }),
          el('span', { class: 'skeleton skeleton--panel' }),
        ]),
        el('div', { class: 'player-skeleton__block' }, [
          el('span', { class: 'skeleton skeleton--line skeleton--w30' }),
          el('span', { class: 'skeleton skeleton--panel skeleton--panel-sm' }),
        ]),
      ]),
    );
  }

  /** @param {import('../api/types.js').PlayerRecord} player */
  function renderProfile(player) {
    const stats = player.stats;
    const gallery = player.gallery;
    const liveLocation = player.online && (player.currentServer || player.currentMap);

    const profile = el('div', { class: 'profile' }, [
      el('section', { class: 'profile-hero' }, [
        el('div', { class: 'profile-hero__cover' }, [
          el('img', {
            src: player.cover,
            alt: '',
            decoding: 'async',
            draggable: false,
          }),
          el('span', { class: 'profile-hero__shade' }),
          el('span', { class: 'badge badge--demo', text: 'ДЕМО-АНКЕТА' }),
          liveLocation
            ? el('div', { class: 'profile-live', attrs: { 'aria-label': 'Текущая игра' } }, [
                el('span', { class: 'profile-live__label', text: 'СЕРВЕР' }),
                player.currentServer
                  ? el('span', { class: 'profile-live__server', text: player.currentServer })
                  : null,
                player.currentMap
                  ? el('span', { class: 'profile-live__map', text: player.currentMap })
                  : null,
              ])
            : null,
        ]),
        el('div', { class: 'profile-hero__identity' }, [
          el('div', { class: 'profile-hero__avatar-wrap' }, [
            avatar(player.avatar, {
              alt: `Аватар игрока ${player.nick}`,
              className: 'profile-hero__avatar',
            }),
          ]),
          el('h1', { class: 'profile-hero__nick', text: player.nick }),
          el('p', { class: 'profile-hero__meta' }, [
            el('span', {
              text: formatLastSeen(stats.lastSeenHoursAgo, false),
            }),
          ]),
        ]),
      ]),
      el('div', { class: 'profile-body' }, [
        el('section', { class: 'section' }, [
          sectionTitle('О себе'),
          el('div', { class: 'text-card' }, [
            el('p', { text: player.description }),
          ]),
        ]),

        el('div', { class: 'stat-tiles' }, [
          statTile(formatNumber(stats.points), 'очков DDNet'),
          statTile(formatRank(stats.globalRank), 'в мире'),
        ]),

        gallery.length
          ? el('section', { class: 'section' }, [
              sectionTitle('Галерея', {
                extra: el('span', {
                  class: 'section-note',
                  text: `${formatMaterials(gallery.length)} · демо`,
                }),
              }),
              el(
                'div',
                { class: 'gallery' },
                gallery.map((item, index) => galleryTile(item, index, gallery)),
              ),
            ])
          : null,

        el('section', { class: 'section' }, [
          sectionTitle('Статистика DDNet'),
          el(
            'dl',
            { class: 'info-card' },
            [
              ['clock', 'Время в игре', formatHours(stats.hours)],
              [
                'globe',
                'Последний вход',
                formatLastSeen(stats.lastSeenHoursAgo, false),
              ],
            ].map(([iconName, label, value]) =>
              el('div', { class: 'info-row' }, [
                el('span', { class: 'info-row__icon' }, icon(iconName, { size: 18 })),
                el('dt', { class: 'info-row__label', text: label }),
                el('dd', { class: 'info-row__value', text: value }),
              ]),
            ),
          ),
        ]),

        demoNotice(),
      ]),
    ]);

    content.replaceChildren(profile);
    view.appendChild(actionBar(player));
  }

  /** @param {import('../api/types.js').GalleryItem} item @param {number} index @param {import('../api/types.js').GalleryItem[]} gallery */
  function galleryTile(item, index, gallery) {
    const isVideo = item.type === 'video';

    return el(
      'button',
      {
        class: `gallery__item${isVideo ? ' gallery__item--video' : ''}`,
        type: 'button',
        attrs: {
          'aria-label': `${isVideo ? 'Открыть видео' : 'Открыть изображение'}: ${item.caption}`,
        },
        on: {
          click: () => {
            telegram.haptic('light');
            openLightbox(gallery, index);
          },
        },
      },
      [
        el('img', {
          src: isVideo ? item.poster : item.src,
          alt: '',
          loading: 'lazy',
          decoding: 'async',
          draggable: false,
        }),
        el('span', { class: 'gallery__shade' }),
        isVideo
          ? el('span', { class: 'gallery__play' }, icon('play', { size: 20 }))
          : null,
        isVideo && item.duration
          ? el('span', { class: 'gallery__duration', text: item.duration })
          : null,
        el('span', { class: 'gallery__type' }, icon(isVideo ? 'video' : 'image', { size: 15 })),
      ],
    );
  }

  /** @param {import('../api/types.js').PlayerRecord} player */
  function actionBar(player) {
    const copyButton = el(
      'button',
      {
        class: 'btn btn--secondary btn--icon action-bar__icon',
        type: 'button',
        attrs: { 'aria-label': 'Скопировать ник', title: 'Скопировать ник' },
        on: {
          click: async () => {
            telegram.haptic('light');
            const ok = await copyText(player.nick);
            showToast(ok ? `Ник ${player.nick} скопирован` : 'Не удалось скопировать ник', {
              iconName: ok ? 'copy' : 'alert',
              tone: ok ? 'default' : 'danger',
            });
          },
        },
      },
      icon('copy', { size: 20 }),
    );

    return el('div', { class: 'action-bar' }, [
      el('div', { class: 'action-bar__inner' }, [
        copyButton,
        button({
          label: 'Поделиться анкетой',
          variant: 'primary',
          iconName: 'share',
          className: 'action-bar__share',
          onClick: () => shareProfile(player),
        }),
      ]),
    ]);
  }

  /** @param {import('../api/types.js').PlayerRecord} player */
  async function shareProfile(player) {
    telegram.haptic('light');

    const url = new URL(window.location.href);
    url.hash = `#/player/${encodeURIComponent(player.id)}`;
    const text = `${player.nick} — демо-анкета DDNet.`;

    if (navigator.share) {
      try {
        await navigator.share({ title: `${player.nick} · DDNet`, text, url: url.toString() });
        return;
      } catch (error) {
        if (error?.name === 'AbortError') return;
      }
    }

    const ok = await copyText(url.toString());
    showToast(ok ? 'Ссылка на анкету скопирована' : 'Не удалось скопировать ссылку', {
      iconName: ok ? 'check' : 'alert',
      tone: ok ? 'default' : 'danger',
    });
  }

  /** @param {any} error */
  function renderError(error) {
    const code = error?.code;
    const known = code === 'not_found' || code === 'not_approved';
    const title =
      code === 'not_found'
        ? 'Анкета не найдена'
        : code === 'not_approved'
          ? 'Анкета недоступна'
          : 'Не удалось загрузить анкету';

    const text =
      code === 'not_found'
        ? 'Возможно, ссылка устарела или анкета была удалена.'
        : code === 'not_approved'
          ? 'Анкета не прошла модерацию. В каталоге показываются только одобренные профили.'
          : (API_ERROR_TEXT[code] ?? API_ERROR_TEXT.server);

    if (!known) telegram.notify('error');

    const actions = [
      button({
        label: 'К списку анкет',
        variant: 'primary',
        iconName: 'arrowLeft',
        onClick: goBack,
      }),
    ];

    if (!known) {
      actions.push(
        button({
          label: 'Повторить',
          variant: 'secondary',
          iconName: 'refresh',
          onClick: () => load(),
        }),
      );
    }

    content.replaceChildren(
      el('div', { class: 'player-error' }, [
        stateView({
          iconName: code === 'not_found' ? 'user' : code === 'not_approved' ? 'lock' : 'alert',
          title,
          text,
          tone: known ? 'default' : 'danger',
          actions,
        }),
      ]),
    );
  }

  return () => {
    telegram.setBackButton(false);
  };
}

/** @param {string} value @param {string} label */
function statTile(value, label) {
  return el('div', { class: 'stat-tile' }, [
    el('span', { class: 'stat-tile__value', text: value }),
    el('span', { class: 'stat-tile__label', text: label }),
  ]);
}
