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
  button,
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
  let votePending = false;
  let currentIsAdmin = false;

  const view = el('div', { class: 'view view--player' }, [
    appHeader({
      title: 'Анкета игрока',
      centered: true,
      onBack: goBack,
      actions: [
        { iconName: 'info', label: 'О приложении', onClick: () => openAboutSheet() },
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
      const isAdmin = await playersApi.isAdmin();
      if (signal.aborted) return;
      currentIsAdmin = isAdmin;
      renderProfile(player, isAdmin);
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
  function renderProfile(player, isAdmin = false) {
    const stats = player.stats;
    const gallery = player.gallery;
    const liveLocation = player.online && (player.currentServer || player.currentMap);
    const statTiles = [];
    if (stats.points !== null) statTiles.push(statTile(formatNumber(stats.points), 'очков DDNet'));
    if (stats.globalRank !== null) statTiles.push(statTile(formatRank(stats.globalRank), 'в мире'));
    const statisticsRows = [];
    if (stats.hours !== null) statisticsRows.push(['clock', 'Время в игре', formatHours(stats.hours)]);
    if (stats.lastSeenHoursAgo !== null) {
      statisticsRows.push(['globe', 'Последний вход', formatLastSeen(stats.lastSeenHoursAgo, false)]);
    }

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
          el('h1', { class: 'profile-hero__nick', text: player.nick }),
          stats.lastSeenHoursAgo !== null
            ? el('p', { class: 'profile-hero__meta' }, [
                el('span', { text: formatLastSeen(stats.lastSeenHoursAgo, false) }),
              ])
            : null,
        ]),
      ]),
      el('div', { class: 'profile-body' }, [
        el('section', { class: 'section' }, [
          sectionTitle('О себе'),
          el('div', { class: 'text-card' }, [
            el('p', { text: player.description }),
          ]),
        ]),

        statTiles.length ? el('div', { class: 'stat-tiles' }, statTiles) : null,

        gallery.length
          ? el('section', { class: 'section' }, [
              sectionTitle('Галерея', {
                extra: el('span', {
                  class: 'section-note',
                  text: formatMaterials(gallery.length),
                }),
              }),
              el(
                'div',
                { class: 'gallery' },
                gallery.map((item, index) => galleryTile(item, index, gallery)),
              ),
            ])
          : null,

        statisticsRows.length ? el('section', { class: 'section' }, [
          sectionTitle('Статистика DDNet'),
          el(
            'dl',
            { class: 'info-card' },
            statisticsRows.map(([iconName, label, value]) =>
              el('div', { class: 'info-row' }, [
                el('span', { class: 'info-row__icon' }, icon(iconName, { size: 18 })),
                el('dt', { class: 'info-row__label', text: label }),
                el('dd', { class: 'info-row__value', text: value }),
              ]),
            ),
          ),
        ]) : null,

        ratingSection(player),

        isAdmin ? el('section', { class: 'section profile-admin-actions' }, [
          button({
            label: 'Удалить анкету',
            variant: 'danger',
            className: 'btn--block',
            onClick: () => deleteProfile(player),
          }),
        ]) : null,

      ]),
    ]);

    content.replaceChildren(profile);
    view.appendChild(actionBar(player));
  }

  function ratingSection(player) {
    const rating = player.rating ?? {
      count: 0, average: null, myScore: null, changeAt: null, changeUsed: false,
    };
    const hasTelegramAuth = Boolean(window.Telegram?.WebApp?.initData);
    const now = Math.floor(Date.now() / 1000);
    const canVote = hasTelegramAuth && (
      rating.myScore === null
      || (!rating.changeUsed && rating.changeAt !== null && now >= rating.changeAt)
    );
    let hint;
    if (!hasTelegramAuth) {
      hint = 'Чтобы проголосовать, открой анкету внутри Telegram.';
    } else if (rating.myScore === null) {
      hint = 'Один голос на анкету. Изменить его можно через неделю — только один раз.';
    } else if (rating.changeUsed) {
      hint = `Твоя оценка: ${rating.myScore}. Изменение уже использовано.`;
    } else if (rating.changeAt !== null && now < rating.changeAt) {
      const date = new Date(rating.changeAt * 1000).toLocaleString('ru-RU', {
        day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit',
      });
      hint = `Твоя оценка: ${rating.myScore}. Изменить её можно после ${date}.`;
    } else {
      hint = `Твоя оценка: ${rating.myScore}. Можно изменить её один раз.`;
    }

    const average = rating.average === null
      ? '—'
      : rating.average.toLocaleString('ru-RU', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    const scores = Array.from({ length: 7 }, (_, index) => index + 1).map((score) => {
      const selected = rating.myScore === score;
      return el('button', {
        class: `rating-score${selected ? ' rating-score--selected' : ''}`,
        type: 'button',
        attrs: {
          'aria-label': `Поставить оценку ${score}`,
          'aria-pressed': String(selected),
          disabled: !canVote || votePending,
        },
        on: { click: () => submitVote(player, score) },
      }, String(score));
    });

    return el('section', { class: 'section rating-section' }, [
      sectionTitle('Оценка анкеты'),
      el('div', { class: 'rating-card' }, [
        el('div', { class: 'rating-summary' }, [
          el('strong', { class: 'rating-summary__average', text: average }),
          el('span', { class: 'rating-summary__label', text: `Средняя оценка · ${voteCountLabel(rating.count)}` }),
        ]),
        el('div', { class: 'rating-scores', attrs: { role: 'group', 'aria-label': 'Оценка от 1 до 7' } }, scores),
        el('p', { class: 'rating-hint', text: hint }),
      ]),
    ]);
  }

  function voteCountLabel(count) {
    const lastTwo = count % 100;
    const last = count % 10;
    const word = lastTwo >= 11 && lastTwo <= 14
      ? 'голосов'
      : last === 1
        ? 'голос'
        : last >= 2 && last <= 4
          ? 'голоса'
          : 'голосов';
    return `${count} ${word}`;
  }

  async function submitVote(player, score) {
    if (votePending) return;
    votePending = true;
    const scrollY = window.scrollY;
    try {
      const currentScore = player.rating?.myScore;
      const confirmText = currentScore === null || currentScore === undefined
        ? `Ты уверен, что хочешь поставить оценку ${score}? Изменить голос можно будет один раз и не раньше чем через неделю.`
        : `Ты уверен, что хочешь изменить оценку с ${currentScore} на ${score}? После этого поменять её больше нельзя.`;
      if (!await telegram.confirm(confirmText)) return;
      const result = await playersApi.votePlayer(player.id, score);
      player.rating = result.rating;
      votePending = false;
      renderProfile(player, currentIsAdmin);
      window.scrollTo(0, scrollY);
      const messages = {
        created: 'Голос учтён',
        changed: 'Оценка изменена',
        same: 'У тебя уже стоит эта оценка',
        too_early: 'Изменить оценку можно только через неделю после голоса',
        change_used: 'Голос можно изменить только один раз',
      };
      showToast(messages[result.outcome] || 'Голос учтён', { iconName: 'check' });
      telegram.notify('success');
    } catch (error) {
      showToast(error?.message || 'Не удалось отправить голос', {
        iconName: 'alert',
        tone: 'danger',
      });
    } finally {
      votePending = false;
    }
  }

  async function deleteProfile(player) {
    if (!window.confirm(`Удалить анкету ${player.nick}? Это действие нельзя отменить.`)) return;
    try {
      await playersApi.deletePlayer(player.id);
      showToast('Анкета удалена', { iconName: 'check' });
      goBack();
    } catch (error) {
      showToast(error?.message || 'Не удалось удалить анкету', {
        iconName: 'alert',
        tone: 'danger',
      });
    }
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
    const text = `${player.nick} — анкета игрока DDNet.`;

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
