/**
 * Реестр активного оверлея (шторка или лайтбокс).
 * Нужен, чтобы кнопка «Назад» и смена маршрута сначала закрывали модальное окно,
 * а не оставляли его висеть поверх новой страницы.
 */

let activeClose = null;

/** @param {() => void} close */
export function setActiveOverlay(close) {
  activeClose = close;
}

/** @param {() => void} close */
export function clearActiveOverlay(close) {
  if (activeClose === close) activeClose = null;
}

/** @returns {boolean} true, если что-то закрыли */
export function closeActiveOverlay() {
  if (!activeClose) return false;
  const close = activeClose;
  activeClose = null;
  close();
  return true;
}

export function hasActiveOverlay() {
  return Boolean(activeClose);
}
