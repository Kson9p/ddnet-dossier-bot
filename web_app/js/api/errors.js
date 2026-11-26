/** Ошибки слоя данных с понятными кодами для интерфейса. */
export class PlayersApiError extends Error {
  /**
   * @param {'network' | 'server' | 'not_found' | 'not_approved' | 'invalid_data' | 'forbidden'} code
   * @param {string} message
   * @param {{ status?: number }} [options]
   */
  constructor(code, message, options = {}) {
    super(message);
    this.name = 'PlayersApiError';
    this.code = code;
    this.status = options.status;
  }
}

export const API_ERROR_TEXT = {
  network: 'Нет связи с сервером. Проверьте подключение и попробуйте ещё раз.',
  server: 'Сервер не смог ответить. Попробуйте позже.',
  not_found: 'Анкета не найдена или была удалена.',
  not_approved: 'Эта анкета недоступна: она не прошла модерацию.',
  invalid_data: 'Сервер вернул данные в неожиданном формате.',
  forbidden: 'Нет прав для этого действия.',
};
