/**
 * Тонкая интеграция с клиентским SDK Telegram Mini Apps.
 *
 * SDK — это не Bot API: здесь нет токенов, идентификаторов и запросов к боту.
 * Если страница открыта в обычном браузере, все методы работают как заглушки.
 */

import { closeActiveOverlay } from './ui/overlayRegistry.js';

let initialized = false;
let pollTimer = 0;
let backBound = false;
let backVisible = false;
let backHandler = null;

function sdk() {
  return window.Telegram?.WebApp ?? null;
}

function insideTelegram() {
  const app = sdk();
  return Boolean(app && typeof app.platform === 'string' && app.platform !== 'unknown');
}

/** @param {string} version */
function supports(version) {
  try {
    return sdk()?.isVersionAtLeast?.(version) === true;
  } catch {
    return false;
  }
}

function bindBackButton() {
  const app = sdk();
  if (!app?.BackButton || backBound || !supports('6.1')) return;
  app.BackButton.onClick(() => {
    // Сначала закрываем шторку или лайтбокс, если они открыты.
    if (closeActiveOverlay()) return;
    backHandler?.();
  });
  backBound = true;
}

function applyBackButton() {
  const app = sdk();
  if (!app?.BackButton || !supports('6.1')) return;
  bindBackButton();
  try {
    if (backVisible) app.BackButton.show();
    else app.BackButton.hide();
  } catch {
    // В старых версиях клиента BackButton может отсутствовать.
  }
}

function syncViewport() {
  const app = sdk();
  const height = app?.viewportStableHeight || window.innerHeight;
  document.documentElement.style.setProperty('--tg-viewport-height', `${Math.round(height)}px`);
}

function init() {
  if (initialized) return;

  const app = sdk();
  if (!app) {
    if (pollTimer) return;
    let attempts = 0;
    // SDK подключается с CDN и может появиться чуть позже модуля приложения.
    pollTimer = window.setInterval(() => {
      attempts += 1;
      if (sdk()) {
        window.clearInterval(pollTimer);
        pollTimer = 0;
        init();
      } else if (attempts >= 24) {
        window.clearInterval(pollTimer);
        pollTimer = 0;
      }
    }, 50);
    return;
  }

  initialized = true;

  // В обычном браузере SDK отдаёт platform = 'unknown'. Ничего не настраиваем,
  // чтобы не получать предупреждения о неподдерживаемых методах.
  if (!insideTelegram()) return;

  document.documentElement.dataset.telegram = 'true';

  try {
    app.ready?.();
    app.expand?.();
    if (supports('6.1')) {
      app.setHeaderColor?.('#e8f3ff');
      app.setBackgroundColor?.('#eaf3ff');
    }
    if (supports('7.10')) {
      app.setBottomBarColor?.('#eaf3ff');
    }
  } catch {
    // Не критично для работы интерфейса.
  }

  bindBackButton();
  applyBackButton();
  syncViewport();

  try {
    app.onEvent?.('viewportChanged', syncViewport);
  } catch {
    // Игнорируем: событие доступно не во всех клиентах.
  }

  window.addEventListener('resize', syncViewport, { passive: true });
}

/** @param {boolean} visible @param {(() => void) | null} [handler] */
function setBackButton(visible, handler = null) {
  backVisible = Boolean(visible);
  backHandler = handler;
  applyBackButton();
}

/** @param {'light' | 'medium' | 'heavy' | 'rigid' | 'soft'} [style] */
function haptic(style = 'light') {
  if (!supports('6.1')) return;
  try {
    sdk()?.HapticFeedback?.impactOccurred(style);
  } catch {
    // Гарптика недоступна — молча пропускаем.
  }
}

/** Show a native Telegram confirmation dialog, with a browser fallback. */
function confirm(message) {
  const app = sdk();
  if (!insideTelegram() || !supports('6.2') || typeof app?.showConfirm !== 'function') {
    return Promise.resolve(window.confirm(message));
  }
  return new Promise((resolve) => {
    try {
      app.showConfirm(message, (accepted) => resolve(accepted === true));
    } catch {
      resolve(window.confirm(message));
    }
  });
}

/** Open a Telegram link in the Telegram client when available. */
function openTelegramLink(url) {
  const app = sdk();
  if (insideTelegram() && typeof app?.openTelegramLink === 'function') {
    app.openTelegramLink(url);
    return;
  }
  window.open(url, '_blank', 'noopener,noreferrer');
}

/** @param {'error' | 'success' | 'warning'} [type] */
function notify(type = 'success') {
  if (!supports('6.1')) return;
  try {
    sdk()?.HapticFeedback?.notificationOccurred(type);
  } catch {
    // Игнорируем.
  }
}

export const telegram = {
  init,
  setBackButton,
  haptic,
  notify,
  confirm,
  openTelegramLink,
  get available() {
    return insideTelegram();
  },
};
