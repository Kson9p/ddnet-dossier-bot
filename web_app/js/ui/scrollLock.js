let lockCount = 0;

/** Блокирует прокрутку фона, пока открыт оверлей. */
export function lockScroll() {
  lockCount += 1;
  if (lockCount > 1) return;

  const gap = window.innerWidth - document.documentElement.clientWidth;
  document.documentElement.classList.add('is-locked');
  if (gap > 0) {
    document.documentElement.style.setProperty('--scrollbar-gap', `${gap}px`);
  }
}

/** Снимает блокировку после закрытия последнего оверлея. */
export function unlockScroll() {
  if (lockCount === 0) return;
  lockCount -= 1;
  if (lockCount > 0) return;

  document.documentElement.classList.remove('is-locked');
  document.documentElement.style.removeProperty('--scrollbar-gap');
}
