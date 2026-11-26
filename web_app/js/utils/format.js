const numberFormatter = new Intl.NumberFormat('ru-RU');

/** @param {number} value */
export function formatNumber(value) {
  const number = Number(value);
  return numberFormatter.format(Number.isFinite(number) ? number : 0);
}

/** @param {number} rank */
export function formatRank(rank) {
  return rank > 0 ? `#${formatNumber(rank)}` : '—';
}

/** @param {number} hours */
export function formatHours(hours) {
  return `${formatNumber(hours)} ч`;
}

/**
 * Русские формы множественного числа.
 * @param {number} count
 * @param {[string, string, string]} forms
 */
export function plural(count, forms) {
  const abs = Math.abs(count) % 100;
  const last = abs % 10;
  if (abs > 10 && abs < 20) return forms[2];
  if (last > 1 && last < 5) return forms[1];
  if (last === 1) return forms[0];
  return forms[2];
}

/** @param {number} count */
export function formatMaps(count) {
  return `${formatNumber(count)} ${plural(count, ['карта', 'карты', 'карт'])}`;
}

/** @param {number} count */
export function formatMaterials(count) {
  return `${formatNumber(count)} ${plural(count, ['материал', 'материала', 'материалов'])}`;
}

/**
 * @param {number} hoursAgo
 * @param {boolean} online
 */
export function formatLastSeen(hoursAgo, online) {
  if (online) return 'в сети';
  if (!Number.isFinite(hoursAgo) || hoursAgo < 0) return 'давно';

  const hours = Math.max(0, Math.round(hoursAgo));
  if (hours < 1) return 'только что';
  if (hours < 24) return `${formatNumber(hours)} ч назад`;

  const days = Math.floor(hours / 24);
  if (days < 30) {
    return `${formatNumber(days)} ${plural(days, ['день', 'дня', 'дней'])} назад`;
  }
  return 'давно';
}

/** @param {number} year */
export function formatJoinedYear(year) {
  return Number.isFinite(year) && year > 0 ? `с ${year} года` : '—';
}

/** @param {number} points */
export function formatPoints(points) {
  return `${formatNumber(points)} ${plural(points, ['очко', 'очка', 'очков'])}`;
}
