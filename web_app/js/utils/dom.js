/** Безопасное создание DOM-узлов без innerHTML для пользовательских данных. */

/**
 * @param {string} tag
 * @param {Record<string, any>} [props]
 * @param {any} [children]
 * @returns {HTMLElement}
 */
export function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);

  for (const [key, value] of Object.entries(props)) {
    if (value === null || value === undefined || value === false) continue;

    if (key === 'class') {
      node.className = value;
    } else if (key === 'text') {
      node.textContent = String(value);
    } else if (key === 'dataset') {
      Object.assign(node.dataset, value);
    } else if (key === 'on') {
      for (const [event, handler] of Object.entries(value)) {
        node.addEventListener(event, handler);
      }
    } else if (key === 'attrs') {
      for (const [attr, attrValue] of Object.entries(value)) {
        if (attrValue === null || attrValue === undefined || attrValue === false) continue;
        node.setAttribute(attr, attrValue === true ? '' : String(attrValue));
      }
    } else if (key in node) {
      node[key] = value;
    } else {
      node.setAttribute(key, value === true ? '' : String(value));
    }
  }

  append(node, children);
  return node;
}

/**
 * @param {Node} parent
 * @param {any} children
 */
export function append(parent, children) {
  if (children === null || children === undefined || children === false) return;
  if (Array.isArray(children)) {
    for (const child of children) append(parent, child);
    return;
  }
  if (children instanceof Node) {
    parent.appendChild(children);
    return;
  }
  parent.appendChild(document.createTextNode(String(children)));
}

/** @param {any} children */
export function fragment(children) {
  const node = document.createDocumentFragment();
  append(node, children);
  return node;
}

/** @param {Element | null} node */
export function clear(node) {
  if (node) node.replaceChildren();
}

/**
 * @param {string} selector
 * @param {ParentNode} [scope]
 */
export function qs(selector, scope = document) {
  const node = scope.querySelector(selector);
  if (!node) throw new Error(`Не найден элемент: ${selector}`);
  return node;
}

/** @param {() => void} fn @param {number} delay */
export function debounce(fn, delay) {
  let timer = 0;
  const debounced = (...args) => {
    clearTimeout(timer);
    timer = window.setTimeout(() => fn(...args), delay);
  };
  debounced.cancel = () => clearTimeout(timer);
  return debounced;
}

/** @param {string} text */
export async function copyText(text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Переходим к запасному способу ниже.
  }

  try {
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand('copy');
    area.remove();
    return ok;
  } catch {
    return false;
  }
}
