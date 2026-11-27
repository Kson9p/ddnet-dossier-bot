const NS = 'http://www.w3.org/2000/svg';

/**
 * Набор линейных иконок в стиле Telegram (stroke-based).
 * Разметка статическая и доверенная, поэтому innerHTML здесь безопасен.
 */
const PATHS = {
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.3-3.3"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  arrowLeft: '<path d="M19 12H5"/><path d="m12 19-7-7 7-7"/>',
  chevronRight: '<path d="m9 18 6-6-6-6"/>',
  chevronLeft: '<path d="m15 18-6-6 6-6"/>',
  chevronDown: '<path d="m6 9 6 6 6-6"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
  more: '<circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/>',
  share:
    '<path d="M12 15V4"/><path d="m7.5 8.5 4.5-4.5 4.5 4.5"/><path d="M5 14v5a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-5"/>',
  copy:
    '<rect x="9" y="9" width="11" height="11" rx="2.5"/><path d="M5.5 15H4.8A1.8 1.8 0 0 1 3 13.2V4.8A1.8 1.8 0 0 1 4.8 3h8.4A1.8 1.8 0 0 1 15 4.8v.7"/>',
  play: '<path d="M8 5.2v13.6L19 12 8 5.2Z" fill="currentColor" stroke="none"/>',
  trophy:
    '<path d="M8 21h8"/><path d="M12 17v4"/><path d="M7 4h10v4.5a5 5 0 0 1-10 0V4Z"/><path d="M7 6H4v1.5A3.5 3.5 0 0 0 7.5 11"/><path d="M17 6h3v1.5A3.5 3.5 0 0 1 16.5 11"/>',
  map: '<path d="M9 3 3 5v16l6-2 6 2 6-2V3l-6 2-6-2Z"/><path d="M9 3v16M15 5v16"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.2 2"/>',
  users:
    '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.9"/><path d="M16 3.1a4 4 0 0 1 0 7.8"/>',
  shield:
    '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 3v6h-6"/>',
  alert: '<circle cx="12" cy="12" r="9"/><path d="M12 7.5V13"/><path d="M12 16.5h.01"/>',
  check: '<path d="m5 13 4 4L19 7"/>',
  image:
    '<rect x="3" y="3" width="18" height="18" rx="2.5"/><circle cx="8.5" cy="8.5" r="1.8"/><path d="m21 15-5-5L5 21"/>',
  video:
    '<rect x="2.5" y="6" width="13" height="12" rx="2.5"/><path d="m15.5 10 5.5-3v10l-5.5-3"/>',
  sparkles:
    '<path d="m12 3 1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8L12 3Z"/><path d="M19 16.5 19.7 18l1.5.7-1.5.7L19 21l-.7-1.6-1.5-.7 1.5-.7.7-1.5Z"/>',
  lock:
    '<rect x="4" y="10" width="16" height="11" rx="2.5"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/><path d="M12 14.5v2.5"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4.5 21a7.5 7.5 0 0 1 15 0"/>',
  globe:
    '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a15 15 0 0 1 0 18a15 15 0 0 1 0-18Z"/>',
  external:
    '<path d="M14 4h6v6"/><path d="M20 4 11 13"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
};

/**
 * @param {keyof typeof PATHS} name
 * @param {{ size?: number, className?: string, strokeWidth?: number }} [options]
 */
export function icon(name, options = {}) {
  const { size = 24, className = '', strokeWidth = 2 } = options;
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', String(size));
  svg.setAttribute('height', String(size));
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', String(strokeWidth));
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  if (className) svg.setAttribute('class', className);
  svg.innerHTML = PATHS[name] ?? '';
  return svg;
}
