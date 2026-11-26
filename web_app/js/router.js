import { telegram } from './telegram.js';
import { closeActiveOverlay } from './ui/overlayRegistry.js';

/**
 * Хеш-роутер: работает на любом статическом хостинге и внутри Mini App.
 * Каждый view получает AbortSignal и возвращает функцию очистки.
 */

const scrollPositions = new Map();
const visited = new Set();

let root = null;
let routeDefs = [];
let fallback = null;
let current = null;

function normalizePath(path) {
  if (!path) return '/';
  const withSlash = path.startsWith('/') ? path : `/${path}`;
  return withSlash.length > 1 ? withSlash.replace(/\/+$/, '') : withSlash;
}

function readPath() {
  const raw = window.location.hash.replace(/^#/, '');
  return normalizePath(raw);
}

function matchRoute(path) {
  const parts = path.split('/').filter(Boolean);

  for (const route of routeDefs) {
    const pattern = route.path.split('/').filter(Boolean);
    if (pattern.length !== parts.length) continue;

    /** @type {Record<string, string>} */
    const params = {};
    let matched = true;

    for (let i = 0; i < pattern.length; i += 1) {
      if (pattern[i].startsWith(':')) {
        try {
          params[pattern[i].slice(1)] = decodeURIComponent(parts[i]);
        } catch {
          matched = false;
          break;
        }
      } else if (pattern[i] !== parts[i]) {
        matched = false;
        break;
      }
    }

    if (matched) return { route, params };
  }

  return null;
}

function navigate(path, options = {}) {
  const target = normalizePath(path);
  const hash = `#${target}`;

  if (readPath() === target) return;

  if (options.replace) {
    window.history.replaceState(null, '', hash);
    handleRoute();
  } else {
    window.location.hash = hash;
  }
}

function goBack() {
  if (current?.path !== '/' && visited.has('/') && window.history.length > 1) {
    window.history.back();
  } else {
    navigate('/', { replace: true });
  }
}

function handleRoute() {
  const path = readPath();
  if (current?.path === path) return;

  // Модальные окна не должны переезжать на новую страницу.
  closeActiveOverlay();

  if (current) {
    scrollPositions.set(current.path, window.scrollY);
    current.cleanup();
  }

  const controller = new AbortController();
  telegram.setBackButton(false);

  const matched = matchRoute(path);
  const restore = path === '/' ? (scrollPositions.get('/') ?? 0) : 0;

  if (restore === 0) window.scrollTo(0, 0);

  const context = {
    root,
    params: matched?.params ?? {},
    signal: controller.signal,
    path,
    scrollY: restore,
    goBack,
    navigate,
  };

  let cleanup = null;

  try {
    cleanup = matched ? matched.route.render(context) : fallback.render(context);
  } catch (error) {
    console.error('Не удалось отрисовать маршрут:', error);
    cleanup = fallback.render({ ...context, error });
  }

  current = {
    path,
    cleanup: () => {
      controller.abort();
      if (typeof cleanup === 'function') cleanup();
    },
  };

  visited.add(path);
  document.documentElement.dataset.route = path === '/' ? 'home' : 'player';
}

/**
 * @param {{ root: HTMLElement, routes: Array<{path: string, render: Function}>, fallback: {render: Function} }} options
 */
export function createRouter(options) {
  root = options.root;
  routeDefs = options.routes;
  fallback = options.fallback;

  if (!root) throw new Error('Не найден корневой контейнер приложения');

  if (!window.location.hash) {
    window.history.replaceState(null, '', '#/');
  }

  window.addEventListener('hashchange', handleRoute);
  handleRoute();

  return { navigate, goBack };
}
