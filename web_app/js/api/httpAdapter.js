import { config } from '../config.js';
import { PlayersApiError } from './errors.js';

/**
 * HTTP-адаптер для будущего подключения к собственной серверной базе.
 *
 * Контракт (подробнее в README):
 *   GET {baseUrl}/players?query=&sort=&page=&pageSize=
 *     -> { items: PlayerSummary[], total: number, page: number, pageSize: number }
 *   GET {baseUrl}/players/:id
 *     -> PlayerRecord (полная анкета)
 *
 * Сервер обязан сам отдавать только одобренные анкеты и проверять права.
 * Клиент дополнительно отбрасывает approved !== true как защиту от ошибок.
 * Медиа должны приходить по безопасным URL, которые готовит сервер;
 * Telegram Bot API и токены в браузере не используются.
 */

const VALID_SORTS = new Set(['default', 'points', 'maps']);

/**
 * @param {unknown} value
 * @returns {value is Record<string, any>}
 */
function isObject(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function requireString(value, field) {
  if (typeof value !== 'string' || value.length === 0) {
    throw new PlayersApiError('invalid_data', `Некорректное поле «${field}»`, { status: 502 });
  }
  return value;
}

function optionalNumber(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/** @returns {import('./types.js').PlayerSummary} */
function normalizeSummary(raw) {
  if (!isObject(raw) || raw.approved === false) {
    throw new PlayersApiError('invalid_data', 'Анкета без признака одобрения', { status: 502 });
  }
  if (!isObject(raw.stats)) {
    throw new PlayersApiError('invalid_data', 'Некорректная статистика анкеты', { status: 502 });
  }

  return {
    id: requireString(raw.id, 'id'),
    nick: requireString(raw.nick, 'nick'),
    initials: typeof raw.initials === 'string' ? raw.initials : raw.nick.slice(0, 2).toUpperCase(),
    tagline: typeof raw.tagline === 'string' ? raw.tagline : '',
    online: raw.online === true,
    region: typeof raw.region === 'string' ? raw.region : '',
    avatar: requireString(raw.avatar, 'avatar'),
    cover: requireString(raw.cover, 'cover'),
    badges: Array.isArray(raw.badges) ? raw.badges.filter((b) => typeof b === 'string') : [],
    lastSeenHoursAgo: optionalNumber(raw.lastSeenHoursAgo ?? raw.stats.lastSeenHoursAgo),
    stats: {
      points: optionalNumber(raw.stats.points),
      globalRank: optionalNumber(raw.stats.globalRank),
      mapsFinished: optionalNumber(raw.stats.mapsFinished),
      hours: optionalNumber(raw.stats.hours),
    },
  };
}

/** @returns {import('./types.js').PlayerRecord} */
function normalizeDetail(raw) {
  if (!isObject(raw) || raw.approved !== true) {
    throw new PlayersApiError('not_approved', 'Анкета не одобрена', { status: 403 });
  }
  if (!isObject(raw.stats) || !Array.isArray(raw.gallery)) {
    throw new PlayersApiError('invalid_data', 'Некорректные данные анкеты', { status: 502 });
  }

  const gallery = raw.gallery
    .filter((item) => isObject(item) && (item.type === 'image' || item.type === 'video'))
    .map((item) => ({
      type: item.type,
      src: typeof item.src === 'string' ? item.src : undefined,
      poster: typeof item.poster === 'string' ? item.poster : undefined,
      caption: typeof item.caption === 'string' ? item.caption : '',
      duration: typeof item.duration === 'string' ? item.duration : undefined,
    }))
    .filter((item) => (item.type === 'image' ? Boolean(item.src) : Boolean(item.poster)));

  return {
    id: requireString(raw.id, 'id'),
    nick: requireString(raw.nick, 'nick'),
    initials: typeof raw.initials === 'string' ? raw.initials : raw.nick.slice(0, 2).toUpperCase(),
    tagline: typeof raw.tagline === 'string' ? raw.tagline : '',
    description: typeof raw.description === 'string' ? raw.description : '',
    approved: true,
    online: raw.online === true,
    currentServer: typeof raw.currentServer === 'string' ? raw.currentServer.trim() : '',
    currentMap: typeof raw.currentMap === 'string' ? raw.currentMap.trim() : '',
    region: typeof raw.region === 'string' ? raw.region : '',
    badges: Array.isArray(raw.badges) ? raw.badges.filter((b) => typeof b === 'string') : [],
    stats: {
      points: optionalNumber(raw.stats.points),
      globalRank: optionalNumber(raw.stats.globalRank),
      teamRank: optionalNumber(raw.stats.teamRank),
      hours: optionalNumber(raw.stats.hours),
      mapsFinished: optionalNumber(raw.stats.mapsFinished),
      bestRank: optionalNumber(raw.stats.bestRank),
      favoriteMap: typeof raw.stats.favoriteMap === 'string' ? raw.stats.favoriteMap : '—',
      joinedYear: optionalNumber(raw.stats.joinedYear),
      lastSeenHoursAgo: optionalNumber(raw.stats.lastSeenHoursAgo),
    },
    avatar: requireString(raw.avatar, 'avatar'),
    cover: requireString(raw.cover, 'cover'),
    gallery,
  };
}

/**
 * @param {{ baseUrl?: string, fetchImpl?: typeof fetch }} [options]
 */
export function createHttpPlayersApi(options = {}) {
  const baseUrl = (options.baseUrl ?? config.apiBaseUrl).replace(/\/+$/, '');
  const fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);

  /**
   * @param {string} path
   * @param {AbortSignal} [signal]
   */
  async function request(path, signal) {
    let response;
    try {
      response = await fetchImpl(`${baseUrl}${path}`, {
        method: 'GET',
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
        signal,
      });
    } catch (error) {
      if (error?.name === 'AbortError') throw error;
      throw new PlayersApiError('network', 'Не удалось связаться с сервером');
    }

    if (response.status === 404) {
      throw new PlayersApiError('not_found', 'Анкета не найдена', { status: 404 });
    }
    if (response.status === 403) {
      throw new PlayersApiError('not_approved', 'Анкета не одобрена', { status: 403 });
    }
    if (!response.ok) {
      throw new PlayersApiError('server', `Ошибка сервера (${response.status})`, {
        status: response.status,
      });
    }

    try {
      return await response.json();
    } catch {
      throw new PlayersApiError('invalid_data', 'Ответ сервера не является JSON', {
        status: 502,
      });
    }
  }

  return {
    /** @param {import('./types.js').PlayerListParams} [params] */
    async getPlayers(params = {}) {
      const { query = '', sort = 'default', page = 1, pageSize = config.pageSize, signal } = params;
      const search = new URLSearchParams({
        query: String(query),
        sort: VALID_SORTS.has(sort) ? sort : 'default',
        page: String(Math.max(1, Number(page) || 1)),
        pageSize: String(Math.max(1, Math.min(50, Number(pageSize) || config.pageSize))),
      });

      const payload = await request(`/players?${search.toString()}`, signal);
      if (!isObject(payload) || !Array.isArray(payload.items)) {
        throw new PlayersApiError('invalid_data', 'Некорректный список анкет', { status: 502 });
      }

      // Защита от случайной выдачи неодобренных анкет.
      const items = payload.items.filter((item) => isObject(item) && item.approved !== false);
      const total = Number.isFinite(payload.total) ? payload.total : items.length;

      return {
        items: items.map(normalizeSummary),
        total,
        page: Number.isFinite(payload.page) ? payload.page : Number(page) || 1,
        pageSize: Number.isFinite(payload.pageSize) ? payload.pageSize : Number(pageSize),
        hasMore: Boolean(payload.hasMore),
      };
    },

    /** @param {string} id @param {{ signal?: AbortSignal }} [opts] */
    async getPlayer(id, opts = {}) {
      const payload = await request(`/players/${encodeURIComponent(id)}`, opts.signal);
      return normalizeDetail(payload);
    },
  };
}
