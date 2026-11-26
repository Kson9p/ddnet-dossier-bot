import { el } from '../utils/dom.js';
import { icon } from './icons.js';

let hideTimer = 0;

/**
 * Короткое всплывающее уведомление.
 * @param {string} message
 * @param {{ iconName?: string, tone?: 'default' | 'danger', duration?: number }} [options]
 */
export function showToast(message, options = {}) {
  const { iconName = 'check', tone = 'default', duration = 2600 } = options;
  const root = document.getElementById('toast-root');
  if (!root) return;

  clearTimeout(hideTimer);

  const toast = el('div', { class: `toast toast--${tone}`, attrs: { role: 'status' } }, [
    el('span', { class: 'toast__icon' }, icon(iconName, { size: 18 })),
    el('span', { class: 'toast__text', text: message }),
  ]);

  root.replaceChildren(toast);
  void toast.offsetWidth;
  toast.classList.add('is-visible');

  hideTimer = window.setTimeout(() => {
    toast.classList.remove('is-visible');
    window.setTimeout(() => toast.remove(), 220);
  }, duration);
}
