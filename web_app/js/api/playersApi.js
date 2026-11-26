import { createHttpPlayersApi } from './httpAdapter.js';

/**
 * Единая точка доступа к анкетам для интерфейса.
 *
 * Интерфейс знает только два метода:
 *   playersApi.getPlayers({ query, sort, page, pageSize, signal })
 *   playersApi.getPlayer(id, { signal })
 *
 * Данные загружаются из API бота.
 */

const adapter = createHttpPlayersApi();

export const playersApi = {
  isAdmin: () => adapter.isAdmin(),
  deletePlayer: (id) => adapter.deletePlayer(id),
  /** @param {import('./types.js').PlayerListParams} [params] */
  getPlayers: (params = {}) => adapter.getPlayers(params),

  /** @param {string} id @param {{ signal?: AbortSignal }} [options] */
  getPlayer: (id, options = {}) => adapter.getPlayer(id, options),
};
