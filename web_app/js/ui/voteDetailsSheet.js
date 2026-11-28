import { el } from '../utils/dom.js';
import { button, iconButton } from './components.js';
import { trapFocus } from './focusTrap.js';
import { lockScroll, unlockScroll } from './scrollLock.js';
import { clearActiveOverlay, hasActiveOverlay, setActiveOverlay } from './overlayRegistry.js';
import { showToast } from './toast.js';
import { telegram } from '../telegram.js';

const RATING_LABELS = ['sub 3', 'sub 5', 'ltn', 'mtn', 'htn', 'chad', 'true adam'];

/** @param {{id: string, nick: string}} player @param {() => Promise<Array>} loadVotes */
export function openVoteDetailsSheet(player, loadVotes) {
  if (hasActiveOverlay()) return;

  const app = document.getElementById('app');
  const overlayRoot = document.getElementById('overlay-root');
  if (!overlayRoot) return;
  const previouslyFocused = document.activeElement;
  let closed = false;
  let releaseTrap = null;

  const close = () => {
    if (closed) return;
    closed = true;
    clearActiveOverlay(close);
    document.removeEventListener('keydown', onKeyDown);
    releaseTrap?.();
    if (app) app.inert = false;
    unlockScroll();
    overlay.classList.add('is-closing');
    window.setTimeout(() => {
      overlay.remove();
      if (previouslyFocused instanceof HTMLElement) previouslyFocused.focus();
    }, 180);
  };

  function onKeyDown(event) {
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
    }
  }

  const body = el('div', { class: 'sheet__body vote-details__body', text: 'Загружаю голоса…' });
  const sheet = el('section', {
    class: 'sheet vote-details-sheet',
    attrs: { role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'votes-title', tabindex: '-1' },
  }, [
    el('span', { class: 'sheet__handle', attrs: { 'aria-hidden': 'true' } }),
    el('div', { class: 'sheet__head' }, [
      el('div', {}, [
        el('p', { class: 'sheet__eyebrow', text: player.nick }),
        el('h2', { class: 'sheet__title', id: 'votes-title', text: 'Голоса за анкету' }),
      ]),
      iconButton({ iconName: 'x', label: 'Закрыть', onClick: close }),
    ]),
    body,
    el('div', { class: 'sheet__footer vote-details__footer' }, [
      button({ label: 'Закрыть', variant: 'secondary', onClick: close }),
    ]),
  ]);
  const overlay = el('div', { class: 'overlay overlay--sheet' }, [
    el('div', { class: 'overlay__backdrop', on: { click: close } }),
    sheet,
  ]);

  lockScroll();
  if (app) app.inert = true;
  overlayRoot.appendChild(overlay);
  document.addEventListener('keydown', onKeyDown);
  releaseTrap = trapFocus(sheet);
  setActiveOverlay(close);
  void overlay.offsetWidth;
  overlay.classList.add('is-open');
  sheet.focus();

  loadVotes().then(renderBreakdown).catch((error) => {
    body.replaceChildren(el('p', { class: 'sheet__lead', text: error?.message || 'Не удалось загрузить голоса.' }));
    showToast('Не удалось загрузить список голосов', { iconName: 'alert', tone: 'danger' });
  });

  function renderBreakdown(scores) {
    const rows = scores.map((entry) => {
      const score = Number(entry.score);
      const label = RATING_LABELS[score - 1];
      return el('button', {
        class: 'vote-details__score',
        type: 'button',
        attrs: { disabled: Number(entry.count) === 0 },
        on: { click: () => renderVoters(entry) },
      }, [
        el('span', { class: 'vote-details__score-label', text: label }),
        el('span', { class: 'vote-details__count', text: String(entry.count) }),
        el('span', { class: 'vote-details__arrow', text: '›', attrs: { 'aria-hidden': 'true' } }),
      ]);
    });
    body.replaceChildren(
      el('p', { class: 'sheet__lead', text: 'Выбери оценку, чтобы посмотреть, кто её поставил.' }),
      el('div', { class: 'vote-details__scores' }, rows),
    );
  }

  function renderVoters(entry) {
    const score = Number(entry.score);
    const voters = Array.isArray(entry.voters) ? entry.voters : [];
    const hiddenCount = Math.max(0, Number(entry.count) - voters.length);
    const nodes = [
      button({
        label: 'Все оценки',
        variant: 'ghost',
        iconName: 'arrowLeft',
        className: 'vote-details__back',
        onClick: () => loadVotes().then(renderBreakdown).catch((error) => {
          body.replaceChildren(el('p', { class: 'sheet__lead', text: error?.message || 'Не удалось загрузить голоса.' }));
        }),
      }),
      el('p', { class: 'vote-details__selected', text: `${RATING_LABELS[score - 1]} · ${entry.count} голосов` }),
    ];

    if (voters.length) {
      nodes.push(el('div', { class: 'vote-details__voters' }, voters.map((voter) => {
        const username = typeof voter.username === 'string' ? voter.username.replace(/^@/, '') : '';
        const display = username ? `@${username}` : voter.displayName || 'Пользователь Telegram';
        return username
          ? el('button', {
              class: 'vote-details__voter',
              type: 'button',
              on: { click: () => telegram.openTelegramLink(`https://t.me/${encodeURIComponent(username)}`) },
            }, [
              el('span', { class: 'vote-details__voter-name', text: voter.displayName || display }),
              el('span', { class: 'vote-details__voter-username', text: display }),
            ])
          : el('div', { class: 'vote-details__voter vote-details__voter--plain' }, [
              el('span', { class: 'vote-details__voter-name', text: display }),
              el('span', { class: 'vote-details__voter-username', text: 'Нет username для перехода' }),
            ]);
      })));
    }

    if (hiddenCount > 0) {
      nodes.push(el('p', {
        class: 'vote-details__old-votes',
        text: `${hiddenCount} ${hiddenCount === 1 ? 'голос был оставлен' : 'голоса были оставлены'} до сохранения имён, поэтому автор не отображается.`,
      }));
    } else if (voters.length === 0) {
      nodes.push(el('p', { class: 'vote-details__old-votes', text: 'За эту оценку пока никто не голосовал.' }));
    }
    body.replaceChildren(...nodes);
  }
}
