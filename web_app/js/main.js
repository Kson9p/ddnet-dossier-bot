import { createRouter } from './router.js';
import { telegram } from './telegram.js';
import { renderHome } from './views/home.js';
import { renderPlayer } from './views/player.js';
import { renderNotFound } from './views/notFound.js';

telegram.init();

const root = document.getElementById('app');
if (!root) throw new Error('Не найден контейнер #app');

const router = createRouter({
  root,
  routes: [
    { path: '/', render: renderHome },
    { path: '/player/:id', render: renderPlayer },
  ],
  fallback: { render: renderNotFound },
});

// Мягкая гарптика при открытии анкеты (если доступна в клиенте).
document.addEventListener(
  'click',
  (event) => {
    if (event.target instanceof Element && event.target.closest('a.player-card')) {
      telegram.haptic('light');
    }
  },
  { passive: true },
);

window.addEventListener('unhandledrejection', (event) => {
  if (event.reason?.name !== 'AbortError') {
    console.error('Необработанная ошибка:', event.reason);
  }
});

export { router };
