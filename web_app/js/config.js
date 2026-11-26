/**
 * Настройки приложения.
 *
 * apiMode:
 *   'local' — локальные примеры анкет (по умолчанию);
 *   'http' — запросы к собственному серверу по контракту из README.
 *
 * Чтобы подключить реальную базу, достаточно переключить apiMode на 'http'
 * и указать адрес API. Интерфейс и формат данных останутся прежними.
 */
export const config = Object.freeze({
  apiMode: 'local',
  apiBaseUrl: '/api',
  pageSize: 6,
  localLatency: {
    min: 140,
    max: 320,
  },
});
