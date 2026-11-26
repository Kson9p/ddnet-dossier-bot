import { DEMO_PLAYERS } from '../data/demoPlayers.js';
import { config } from '../config.js';
import { PlayersApiError } from './errors.js';

/**
 * Демонстрационный адаптер.
 * Имитирует сетевые запросы, поиск, сортировку и пагинацию.
 * Наружу отдаёт только анкеты с approved === true.
 */

/** @param {number} ms */
function wait(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('Aborted', 'AbortError'));
      return;
    }

    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);

    function onAbort() {
      clearTimeout(timer);
      reject(new DOMException('Aborted', 'AbortError'));
    }

    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

function simulateLatency(signal) {
  const { min, max } = config.demoLatency;
  const ms = Math.round(min + Math.random() * Math.max(0, max - min));
  return wait(ms, signal);
}

/** @param {import('./types.js').PlayerRecord} record */
function isPublic(record) {
  return Boolean(
    record &&
      record.approved === true &&
      typeof record.id === 'string' &&
      record.id.length > 0 &&
      typeof record.nick === 'string' &&
      record.nick.length > 0 &&
      record.stats,
  );
}

/**
 * @param {import('./types.js').PlayerRecord} record
 * @returns {import('./types.js').PlayerSummary}
 */
function toSummary(record) {
  return {
    id: record.id,
    nick: record.nick,
    initials: record.initials,
    tagline: record.tagline,
    online: record.online,
    region: record.region,
    avatar: record.avatar,
    cover: record.cover,
    badges: [...record.badges],
    lastSeenHoursAgo: record.stats.lastSeenHoursAgo,
    stats: {
      points: record.stats.points,
      globalRank: record.stats.globalRank,
      mapsFinished: record.stats.mapsFinished,
      hours: record.stats.hours,
    },
  };
}

/**
 * @param {import('./types.js').PlayerRecord} record
 * @returns {import('./types.js').PlayerRecord}
 */
function toDetail(record) {
  return {
    ...record,
    badges: [...record.badges],
    stats: { ...record.stats },
    gallery: record.gallery.map((item) => ({ ...item })),
  };
}

/**
 * @param {import('./types.js').PlayerListParams} [params]
 * @returns {Promise<import('./types.js').PlayerListResult>}
 */
async function getPlayers(params = {}) {
  const { query = '', sort = 'default', page = 1, pageSize = config.pageSize, signal } = params;

  await simulateLatency(signal);

  const needle = String(query).trim().toLocaleLowerCase('ru');
  let items = DEMO_PLAYERS.filter(isPublic);

  if (needle) {
    items = items.filter((record) => record.nick.toLocaleLowerCase('ru').includes(needle));
  }

  items = [...items].sort((a, b) => {
    if (sort === 'points') return b.stats.points - a.stats.points;
    if (sort === 'maps') return b.stats.mapsFinished - a.stats.mapsFinished;
    if (a.online !== b.online) return a.online ? -1 : 1;
    return b.stats.points - a.stats.points;
  });

  const total = items.length;
  const safePageSize = Math.max(1, Math.min(50, Number(pageSize) || config.pageSize));
  const safePage = Math.max(1, Number(page) || 1);
  const start = (safePage - 1) * safePageSize;
  const slice = items.slice(start, start + safePageSize);

  return {
    items: slice.map(toSummary),
    total,
    page: safePage,
    pageSize: safePageSize,
    hasMore: start + slice.length < total,
  };
}

/**
 * @param {string} id
 * @param {{ signal?: AbortSignal }} [options]
 * @returns {Promise<import('./types.js').PlayerRecord>}
 */
async function getPlayer(id, options = {}) {
  await simulateLatency(options.signal);

  const record = DEMO_PLAYERS.find((item) => item.id === id);

  if (!record) {
    throw new PlayersApiError('not_found', 'Анкета не найдена', { status: 404 });
  }

  if (!isPublic(record)) {
    throw new PlayersApiError('not_approved', 'Анкета не одобрена', { status: 403 });
  }

  return toDetail(record);
}

export function createDemoPlayersApi() {
  return { getPlayers, getPlayer };
}
