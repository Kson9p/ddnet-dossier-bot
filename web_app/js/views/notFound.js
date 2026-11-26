import { el } from '../utils/dom.js';
import { appHeader, button, stateView } from '../ui/components.js';

/** Резервный экран для неизвестного адреса. */
export function renderNotFound({ root, navigate }) {
  const view = el('div', { class: 'view view--notfound' }, [
    appHeader({
      title: 'Анкеты DDNet',
      subtitle: 'Демо-каталог игроков',
      logo: true,
      titleTag: 'h1',
    }),
    el('main', { class: 'notfound' }, [
      stateView({
        iconName: 'globe',
        title: 'Такой страницы нет',
        text: 'Возможно, ссылка устарела или в адресе есть опечатка.',
        actions: [
          button({
            label: 'На главную',
            variant: 'primary',
            iconName: 'arrowLeft',
            onClick: () => navigate('/', { replace: true }),
          }),
        ],
      }),
    ]),
  ]);

  root.replaceChildren(view);
  return () => {};
}
