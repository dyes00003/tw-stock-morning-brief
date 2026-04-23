const STORAGE_KEY = "tw-stock-brief-reading-mode";
const MODE_ORDER = ["auto", "phone", "tablet", "desktop"];

const modeCopy = {
  auto: "自動偵測",
  phone: "手機滑讀",
  tablet: "平板閱讀",
  desktop: "桌面深讀",
};

export function initReadingMode() {
  const root = document.documentElement;
  const host = document.getElementById("reading-mode-control");
  let preference = getStoredPreference();

  renderControl(host);

  const apply = () => {
    const detectedMode = detectReadingMode();
    const activeMode = preference === "auto" ? detectedMode : preference;

    root.dataset.readingPreference = preference;
    root.dataset.detectedDevice = detectedMode;
    root.dataset.readingMode = activeMode;

    updateControl(host, preference, activeMode, detectedMode);
  };

  host?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-reading-option]");
    if (!button) return;

    const nextPreference = button.dataset.readingOption;
    if (!MODE_ORDER.includes(nextPreference)) return;

    preference = nextPreference;
    storePreference(preference);
    apply();
  });

  window.addEventListener("resize", debounce(apply, 160), { passive: true });
  window.addEventListener("orientationchange", apply, { passive: true });

  apply();
}

function renderControl(host) {
  if (!host) return;

  host.innerHTML = `
    <div class="reading-mode-copy" aria-live="polite">
      <span class="reading-mode-label">閱讀模式</span>
      <strong data-reading-status>自動偵測</strong>
      <span data-reading-detail>依照裝置調整排版</span>
    </div>
    <div class="reading-mode-buttons" role="group" aria-label="切換閱讀模式">
      <button type="button" data-reading-option="auto">自動</button>
      <button type="button" data-reading-option="phone">手機</button>
      <button type="button" data-reading-option="tablet">平板</button>
      <button type="button" data-reading-option="desktop">桌機</button>
    </div>
  `;
}

function updateControl(host, preference, activeMode, detectedMode) {
  if (!host) return;

  const status = host.querySelector("[data-reading-status]");
  const detail = host.querySelector("[data-reading-detail]");
  const buttons = host.querySelectorAll("[data-reading-option]");

  if (status) {
    status.textContent =
      preference === "auto" ? `自動：${modeCopy[activeMode]}` : modeCopy[activeMode];
  }

  if (detail) {
    detail.textContent =
      preference === "auto"
        ? `偵測到 ${modeCopy[detectedMode]}，已套用適合的卡片密度`
        : "已在這台裝置固定使用此模式";
  }

  buttons.forEach((button) => {
    const isActive = button.dataset.readingOption === preference;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });
}

function detectReadingMode() {
  const width = window.innerWidth || document.documentElement.clientWidth || 0;
  const coarsePointer = window.matchMedia?.("(pointer: coarse)").matches ?? false;
  const hoverNone = window.matchMedia?.("(hover: none)").matches ?? false;
  const touchPoints = navigator.maxTouchPoints || 0;
  const touchFirst = coarsePointer || hoverNone || touchPoints > 0;

  if (width <= 760 || (touchFirst && width <= 880)) {
    return "phone";
  }

  if (width <= 1120 || (touchFirst && width <= 1360)) {
    return "tablet";
  }

  return "desktop";
}

function getStoredPreference() {
  try {
    const storedPreference = window.localStorage.getItem(STORAGE_KEY);
    return MODE_ORDER.includes(storedPreference) ? storedPreference : "auto";
  } catch {
    return "auto";
  }
}

function storePreference(preference) {
  try {
    window.localStorage.setItem(STORAGE_KEY, preference);
  } catch {
    // Private browsing or locked-down browsers can block localStorage.
  }
}

function debounce(callback, delay) {
  let timer;

  return () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(callback, delay);
  };
}
