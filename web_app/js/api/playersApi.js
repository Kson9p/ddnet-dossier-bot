import { config } from '../config.js';
import { createDemoPlayersApi } from './demoAdapter.js';
import { createHttpPlayersApi } from './httpAdapter.js';

/**
 * Единая точка доступа к анкетам для интерфейса.
 *
 * Интерфейс знает только два метода:
 *   playersApi.getPlayers({ query, sort, page, pageSize, signal })
 *   playersApi.getPlayer(id, { signal })
 *
 * Реализация выбирается в js/config.js (apiMode: 'demo' | 'http').
 * Благодаря этому замена заглушек на серверную базу не требует правок UI.
 */

const factories = {
  demo: createDemoPlayersApi,
  http: createHttpPlayersApi,
};

const factory = factories[config.apiMode] ?? factories.demo;
const adapter = factory();

export const playersApi = {
  /** @param {import('./types.js').PlayerListParams} [params] */
  getPlayers: (params = {}) => adapter.getPlayers(params),

  /** @param {string} id @param {{ signal?: AbortSignal }} [options] */
  getPlayer: (id, options = {}) => adapter.getPlayer(id, options),
};
