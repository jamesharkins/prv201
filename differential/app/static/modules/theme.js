// Light/dark theme: follows prefers-color-scheme until the user picks one;
// the choice is remembered in localStorage (all storage access is guarded).

const KEY = "differential.theme";

function readStored() {
  try {
    const t = window.localStorage.getItem(KEY);
    return t === "light" || t === "dark" ? t : null;
  } catch {
    return null;
  }
}

function writeStored(t) {
  try {
    window.localStorage.setItem(KEY, t);
  } catch {
    /* storage unavailable (private mode, blocked): the choice lasts for this page only */
  }
}

export function currentTheme() {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

export function initTheme(onChange) {
  const mq = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  const apply = (t) => {
    document.documentElement.setAttribute("data-theme", t);
    if (onChange) onChange(t);
  };
  apply(readStored() || (mq && mq.matches ? "dark" : "light"));
  if (mq) {
    const follow = (e) => {
      if (!readStored()) apply(e.matches ? "dark" : "light");
    };
    if (mq.addEventListener) mq.addEventListener("change", follow);
    else if (mq.addListener) mq.addListener(follow);
  }
  return {
    toggle() {
      const next = currentTheme() === "dark" ? "light" : "dark";
      writeStored(next);
      apply(next);
      return next;
    },
  };
}
