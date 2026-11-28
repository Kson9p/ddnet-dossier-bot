import { el } from '../utils/dom.js';
import { formatLastSeen, formatNumber } from '../utils/format.js';
import { icon } from './icons.js';

/**
 * @param {{ iconName: keyof typeof import('./icons.js').default, label: string, onClick?: (event: Event) => void, className?: string }} options
 */
export function iconButton({ iconName, label, onClick, className = '' }) {
  return el(
    'button',
    {
      class: `icon-button ${className}`.trim(),
      type: 'button',
      attrs: { 'aria-label': label, title: label },
      on: onClick ? { click: onClick } : {},
    },
    icon(iconName, { size: 22 }),
  );
}

/**
 * @param {{ label: string, variant?: 'primary' | 'secondary' | 'ghost', iconName?: string, onClick?: (event: Event) => void, className?: string, type?: string }} options
 */
export function button({ label, variant = 'primary', iconName, onClick, className = '', type = 'button' }) {
  return el(
    'button',
    {
      class: `btn btn--${variant} ${className}`.trim(),
      type,
      on: onClick ? { click: onClick } : {},
    },
    [iconName ? icon(iconName, { size: 19 }) : null, el('span', { text: label })],
  );
}

/**
 * Шапка приложения в стиле Telegram Mini App.
 * @param {{ title: string, subtitle?: string, logo?: boolean, onBack?: () => void, actions?: Array<{iconName: string, label: string, onClick: () => void}>, centered?: boolean, titleTag?: 'h1' | 'div' }} options
 */
export function appHeader({
  title,
  subtitle = '',
  logo = false,
  onBack,
  actions = [],
  centered = false,
  titleTag = 'div',
}) {
  const left = onBack
    ? iconButton({ iconName: 'arrowLeft', label: 'Назад', onClick: onBack })
    : logo
      ? el('span', { class: 'brand-mark', attrs: { 'aria-hidden': 'true' }, text: 'DD' })
      : null;

  return el(
    'header',
    { class: `app-header${centered ? ' app-header--center' : ''}` },
    [
      el('div', { class: 'app-header__side' }, left),
      el('div', { class: 'app-header__titles' }, [
        el(titleTag, { class: 'app-header__title', text: title }),
        subtitle ? el('p', { class: 'app-header__subtitle', text: subtitle }) : null,
      ]),
      el(
        'div',
        { class: 'app-header__actions' },
        actions.map((action) =>
          iconButton({ iconName: action.iconName, label: action.label, onClick: action.onClick }),
        ),
      ),
    ],
  );
}

/**
 * Карточка анкеты в списке.
 * @param {import('../api/types.js').PlayerSummary} player
 */
export function playerCard(player) {
  const stats = [];
  const ratingLabels = ['sub 3', 'sub 5', 'ltn', 'mtn', 'htn', 'chad', 'true adam'];
  const hasRating = player.rating?.count > 0 && Number.isFinite(player.rating.average);
  const roundedRating = hasRating ? Math.max(1, Math.min(7, Math.round(player.rating.average))) : null;
  if (player.stats.points !== null) stats.push(statCell(formatNumber(player.stats.points), 'очков'));
  if (player.stats.hours !== null) stats.push(statCell(formatNumber(player.stats.hours), 'часов'));
  return el(
    'a',
    {
      class: 'player-card',
      href: `#/player/${encodeURIComponent(player.id)}`,
      attrs: { 'aria-label': `Открыть анкету ${player.nick}` },
    },
    [
      el('div', { class: 'player-card__cover' }, [
        el('img', {
          src: player.cover,
          alt: '',
          loading: 'lazy',
          decoding: 'async',
          draggable: false,
        }),
        el('span', { class: 'player-card__shade' }),
        el('div', { class: 'player-card__cover-top' }, [
            player.stats.globalRank !== null
              ? el('span', { class: 'badge badge--rank' }, [
                  icon('trophy', { size: 13 }),
                  `#${formatNumber(player.stats.globalRank)}`,
                ])
              : null,
          player.online
            ? el('span', { class: 'badge badge--online' }, 'онлайн')
            : null,
        ]),
      ]),
      el('div', { class: 'player-card__body' }, [
        el('div', { class: 'player-card__row' }, [
          el('div', { class: 'player-card__titles' }, [
            el('div', { class: 'player-card__nick-row' }, [
              el('h2', { class: 'player-card__nick', text: player.nick }),
              hasRating
                ? el('span', {
                    class: 'player-card__rating',
                    attrs: {
                      title: `Средняя оценка ${player.rating.average.toFixed(1)} из 7 · ${player.rating.count} голосов`,
                      'aria-label': `Средняя оценка ${player.rating.average.toFixed(1)} из 7: ${ratingLabels[roundedRating - 1]}`,
                    },
                    text: `${player.rating.average.toFixed(1)} · ${ratingLabels[roundedRating - 1]}`,
                  })
                : null,
            ]),
            el('span', {
              class: `player-card__category player-card__category--${player.gender}`,
              text: player.gender === 'girl' ? 'Девушка' : 'Парень',
            }),
            player.lastSeenHoursAgo !== null
              ? el('p', {
                  class: 'player-card__meta',
                  text: formatLastSeen(player.lastSeenHoursAgo, false),
                })
              : null,
          ]),
          el('span', { class: 'player-card__chevron' }, icon('chevronRight', { size: 20 })),
        ]),
        stats.length ? el('div', { class: 'player-card__stats' }, stats) : null,
      ]),
    ],
  );
}

/** @param {string} value @param {string} label */
function statCell(value, label) {
  return el('div', { class: 'stat-cell' }, [
    el('span', { class: 'stat-cell__value', text: value }),
    el('span', { class: 'stat-cell__label', text: label }),
  ]);
}

/**
 * @param {string} title
 * @param {{ count?: number, extra?: Node | null }} [options]
 */
export function sectionTitle(title, options = {}) {
  const { count, extra = null } = options;
  return el('div', { class: 'section-head' }, [
    el('h2', { class: 'section-title' }, [
      title,
      count !== undefined ? el('span', { class: 'section-count', text: String(count) }) : null,
    ]),
    extra,
  ]);
}

/** @param {number} index */
export function skeletonCard() {
  return el('div', { class: 'player-card player-card--skeleton', attrs: { 'aria-hidden': 'true' } }, [
    el('div', { class: 'skeleton skeleton--cover' }),
    el('div', { class: 'player-card__body' }, [
      el('div', { class: 'player-card__row' }, [
        el('div', { class: 'skeleton-stack' }, [
          el('span', { class: 'skeleton skeleton--line skeleton--w40' }),
          el('span', { class: 'skeleton skeleton--line skeleton--w60 skeleton--thin' }),
        ]),
      ]),
      el('span', { class: 'skeleton skeleton--line skeleton--w80' }),
      el('span', { class: 'skeleton skeleton--line skeleton--w55 skeleton--thin' }),
      el('div', { class: 'skeleton-stats' }, [
        el('span', { class: 'skeleton skeleton--tile' }),
        el('span', { class: 'skeleton skeleton--tile' }),
        el('span', { class: 'skeleton skeleton--tile' }),
      ]),
    ]),
  ]);
}

export function skeletonList(count = 3) {
  return el(
    'div',
    { class: 'player-list', attrs: { 'aria-busy': 'true', 'aria-label': 'Загрузка анкет' } },
    Array.from({ length: count }, () => skeletonCard()),
  );
}

/**
 * Экран состояния: пусто, ошибка, нет доступа.
 * @param {{ iconName: string, title: string, text: string, actions?: HTMLElement[], tone?: 'default' | 'danger' }} options
 */
export function stateView({ iconName, title, text, actions = [], tone = 'default' }) {
  return el('div', { class: `state state--${tone}` }, [
    el('div', { class: 'state__icon' }, icon(iconName, { size: 30 })),
    el('h2', { class: 'state__title', text: title }),
    el('p', { class: 'state__text', text }),
    actions.length ? el('div', { class: 'state__actions' }, actions) : null,
  ]);
}
