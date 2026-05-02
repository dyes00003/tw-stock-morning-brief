import {
  escapeHtml,
  formatNumber,
  getNewDiscoveries,
  loadLatestReport,
} from "./report-utils.js";
import { initReadingMode } from "./reading-mode.js";

const app = document.getElementById("app");
const newsNavLink = document.getElementById("news-nav-link");
const quickNav = document.querySelector(".quick-nav");

const heatToneMap = {
  偏熱: "heat-hot",
  中偏熱: "heat-hot",
  溫熱: "heat-warm",
  中溫: "heat-cool",
  偏冷: "heat-cool",
};

async function loadReport() {
  try {
    const report = await loadLatestReport();
    render(report);
  } catch (error) {
    app.innerHTML = `
      <section class="loading-card">
        <p class="loading-kicker">載入失敗</p>
        <h2>網站資料還沒準備好</h2>
        <p>請確認 <code>site/data/latest.json</code> 是否存在，或稍後重新整理。</p>
        <p class="meta-note">${escapeHtml(String(error))}</p>
      </section>
    `;
  }
}

function render(report) {
  const discoveries = getNewDiscoveries(report);
  const tradeThemes = Array.isArray(report.themes) ? report.themes : [];
  const tradePicks = Array.isArray(report.topPicks) ? report.topPicks : [];
  const observationThemes = Array.isArray(report.observationThemes) ? report.observationThemes : [];
  const observationStocks = Array.isArray(report.observationStocks) ? report.observationStocks : [];
  const weekRangeLabel = formatWeekRange(report.weekRange);
  const foreignFlowDisplay = formatSignedAmount(report.marketSnapshot.foreignFlowTwdBn);
  const foreignFlowTone = flowTone(foreignFlowDisplay);
  const marketRegime = normalizeMarketRegime(report.marketSnapshot?.marketRegime);
  const tradingPoolLimits = getTradingPoolLimits(marketRegime.mode);
  const tradeThemeHeading = `交易池題材（${tradeThemes.length} / ${tradingPoolLimits.themeLabel}）`;
  const tradeStockHeading = `交易池股票（${tradePicks.length} / ${tradingPoolLimits.stockLabel}）`;
  const regimeBanner = renderRegimeBanner(marketRegime, tradingPoolLimits);
  const themeCards = tradeThemes
    .map((theme, index) => renderTheme(theme, index === 0))
    .join("");

  const focusCards = tradePicks
    .map(
      (pick, index) => `
        <article class="focus-card animate-rise delay-${Math.min(index, 3)}">
          <p class="card-kicker">交易池先看</p>
          <div class="focus-title">
            <h3>${pick.rank}. ${pick.name}</h3>
            <span class="ticker">${pick.ticker}</span>
            <span class="chip">${pick.theme}</span>
          </div>
          <div class="badge-row compact-row">
            ${renderStateBadge(pick.state)}
            ${renderScoreBadge(pick.stockScore, "股票分數")}
            ${renderGateBadge(pick.gateStatus)}
          </div>
          <p class="focus-note">${pick.reason}</p>
          ${pick.alternativeRejected ? `<p class="focus-subnote">勝過替代：${pick.alternativeRejected}</p>` : ""}
        </article>
      `
    )
    .join("");

  const observationThemeCards = observationThemes.length
    ? observationThemes
        .map(
          (theme, index) => `
            <article class="observation-card animate-rise delay-${Math.min(index, 3)}">
              <p class="card-kicker">觀察池題材</p>
              <div class="observation-head">
                <h3>${theme.rank ? `${theme.rank}. ` : ""}${theme.name || "未命名題材"}</h3>
                <div class="badge-row compact-row">
                  ${renderStateBadge(theme.state)}
                  ${renderScoreBadge(theme.themeScore, "題材分數")}
                  ${renderGateBadge(theme.gateStatus)}
                </div>
              </div>
              <p class="body-copy">${theme.observationReason || theme.summary || theme.stance || "這個題材已有證據，但還沒進到交易池。"}</p>
              <div class="observation-meta">
                <div class="info-block compact-card">
                  <p class="info-label">下一個升級條件</p>
                  <p class="info-text">${theme.nextTrigger || formatGateStatus(theme.gateStatus) || "等待更多 tape、法人或事件確認。"}</p>
                </div>
                <div class="info-block compact-card">
                  <p class="info-label">廣度與覆蓋</p>
                  <p class="info-text">${formatBreadthStats(theme.breadthStats) || "目前沒有額外的廣度統計欄位。"}</p>
                </div>
              </div>
            </article>
          `
        )
        .join("")
    : renderObservationEmpty("題材", "目前這版資料還沒有輸出觀察池題材；下次晨報重跑後會在這裡顯示 seed / late 題材。");

  const observationStockCards = observationStocks.length
    ? observationStocks
        .map(
          (stock, index) => `
            <article class="observation-card animate-rise delay-${Math.min(index, 3)}">
              <p class="card-kicker">觀察池股票</p>
              <div class="observation-head">
                <h3>${stock.rank ? `${stock.rank}. ` : ""}${stock.name || "未命名股票"}</h3>
                <div class="badge-row compact-row">
                  <span class="ticker">${stock.ticker || "N/A"}</span>
                  <span class="chip">${stock.theme || "未分類題材"}</span>
                  ${renderStateBadge(stock.state)}
                  ${renderScoreBadge(stock.stockScore, "股票分數")}
                  ${renderGateBadge(stock.gateStatus)}
                </div>
              </div>
              <p class="body-copy">${stock.reason || stock.observationReason || "這檔股票已有題材或事件訊號，但還沒進到交易池名單。"}</p>
              <div class="observation-meta">
                <div class="info-block compact-card">
                  <p class="info-label">升級條件</p>
                  <p class="info-text">${stock.nextTrigger || "等待二階催化、量價確認或更多法人承接。"}</p>
                </div>
                <div class="info-block compact-card">
                  <p class="info-label">替代比較</p>
                  <p class="info-text">${stock.alternativeRejected || "目前沒有提供最近的替代選項比較。"}</p>
                </div>
              </div>
            </article>
          `
        )
        .join("")
    : renderObservationEmpty("股票", "目前這版資料還沒有輸出觀察池股票；之後會在這裡放 seed、late 或 near-miss 個股。");

  const macroCards = report.macroDrivers
    .map(
      (item) => `
        <article class="metric-card">
          <p class="metric-label">${item.label}</p>
          <p class="metric-value ${toneClass(item.tone)}">${item.value}</p>
          <p class="metric-note">${item.detail}</p>
        </article>
      `
    )
    .join("");

  const summaryPoints = report.executiveSummary
    .map((point) => `<li>${point}</li>`)
    .join("");

  const changeItems = report.changesComparedToPrevious.items
    .map(
      (item) => `
        <article class="change-card">
          <p class="card-kicker">與前一日相比</p>
          <h3>${item.title}</h3>
          <p class="body-copy">${item.reason}</p>
        </article>
      `
    )
    .join("");

  const sourceLinks = report.sources
    .map(
      (source) => `
        <li>
          <a href="${source.url}" target="_blank" rel="noreferrer">${source.label}</a>
          <p class="source-note">${source.note || ""}</p>
        </li>
      `
    )
    .join("");

  const discoverySection = discoveries.length
    ? `
      <section class="panel animate-rise delay-1" id="news">
        <div class="section-header">
          <div>
            <p class="section-kicker">本次新消息</p>
            <h2>這次更新新抓到的重點</h2>
            <p>這裡只放本次更新新抓到的新聞或資訊，像公司公告、法說、營收、產能、價格、政策或跨國供應鏈事件；若沒有，就不顯示這一段。</p>
          </div>
          <div class="page-actions">
            <a class="button-link" href="./news.html">打開新消息頁面</a>
          </div>
        </div>
        <div class="discovery-grid">
          ${discoveries
            .slice(0, 3)
            .map(
              (item) => `
                <article class="discovery-card">
                  <p class="card-kicker">${item.scope}</p>
                  <h3>${item.title}</h3>
                  <p class="body-copy">${item.detail}</p>
                  <p class="discovery-why">${item.whyItMatters}</p>
                </article>
              `
            )
            .join("")}
        </div>
      </section>
    `
    : "";

  app.innerHTML = `
    <section class="panel overview animate-rise" id="summary">
      <div class="panel-grid">
        <div class="section-header">
          <div>
            <p class="section-kicker">今日摘要</p>
            <h2>${report.headline}</h2>
            <p>${report.deck}</p>
          </div>
          <div class="badge-row">
            <span class="pill">報告日 ${report.reportDate}</span>
            <span class="pill">操作週 ${weekRangeLabel}</span>
            <span class="pill">股價基準 ${report.priceDate}</span>
            <span class="pill">交易池 ${tradeThemes.length} / ${tradingPoolLimits.themeLabel} 題材</span>
            <span class="pill">交易池 ${tradePicks.length} / ${tradingPoolLimits.stockLabel} 檔</span>
            <span class="pill">觀察池 ${observationThemes.length} 題材 / ${observationStocks.length} 檔</span>
          </div>
        </div>

        <div class="market-strip">
          <article class="metric-card">
            <p class="metric-label">加權指數</p>
            <p class="metric-value tone-up">${formatNumber(report.marketSnapshot.indexClose)}</p>
            <p class="metric-note">單日變動 ${report.marketSnapshot.indexChangePct}%</p>
          </article>
          <article class="metric-card">
            <p class="metric-label">外資現貨</p>
            <p class="metric-value ${foreignFlowTone}">${foreignFlowDisplay} 億</p>
            <p class="metric-note">以 ${report.priceDate} 收盤後資料為準</p>
          </article>
          <article class="metric-card">
            <p class="metric-label">最強族群</p>
            <p class="metric-value">${escapeHtml(report.marketSnapshot.strongestGroup.name)}</p>
            <p class="metric-note">${report.marketSnapshot.strongestGroup.change}</p>
          </article>
          <article class="metric-card regime-card">
            <p class="metric-label">市場 Regime</p>
            <p class="metric-value ${marketRegimeTone(marketRegime.score)}">${marketRegime.score} / 100</p>
            <p class="metric-note">${marketRegime.stance} / ${marketRegime.mode}</p>
            <p class="regime-summary">${marketRegime.summary}</p>
          </article>
        </div>

        <div class="changes-layout">
          <section class="panel-grid">
            <div>
              <p class="section-kicker">總結</p>
              <ul class="summary-points">${summaryPoints}</ul>
            </div>
          </section>
          <section class="panel-grid">
            <div>
              <p class="section-kicker">美國與政策</p>
              <div class="macro-grid">${macroCards}</div>
            </div>
          </section>
        </div>
      </div>
    </section>

    ${discoverySection}

    ${regimeBanner}

    <section class="panel animate-rise delay-1" id="focus">
      <div class="section-header">
        <div>
          <p class="section-kicker">交易池股票</p>
          <h2>${tradeStockHeading}</h2>
          <p>這裡只放已經通過題材與個股 gate 的交易池 top picks；市場 regime 會直接限制這一段的輸出上限。</p>
        </div>
      </div>
      <div class="focus-grid">${focusCards}</div>
    </section>

    <section class="panel animate-rise delay-2" id="observation-stocks">
      <div class="section-header">
        <div>
          <p class="section-kicker">觀察池股票</p>
          <h2>有證據、但還沒完全通過交易 gate 的候選股</h2>
          <p>這裡保留提早卡位線索，但不把它們直接混進交易池 top picks。</p>
        </div>
      </div>
      <div class="observation-grid">${observationStockCards}</div>
    </section>

    <section class="panel animate-rise delay-2" id="themes">
      <div class="section-header">
        <div>
          <p class="section-kicker">交易池題材</p>
          <h2>${tradeThemeHeading}</h2>
          <p>只有通過題材 gate，且 lifecycle 屬於 confirmation / expansion 的題材，才會出現在這一段；市場 regime 偏弱時會直接壓縮上限。</p>
        </div>
      </div>
      <div class="theme-accordion">${themeCards}</div>
    </section>

    <section class="panel animate-rise delay-3" id="observation-themes">
      <div class="section-header">
        <div>
          <p class="section-kicker">觀察池題材</p>
          <h2>還在 seed / late 階段、或只差一項 gate 的題材</h2>
          <p>這裡用來提早追蹤可能升級成主流的子題材，也保留需要降權的 late 題材。</p>
        </div>
      </div>
      <div class="observation-grid">${observationThemeCards}</div>
    </section>

    <section class="panel animate-rise delay-3" id="changes">
      <div class="section-header">
        <div>
          <p class="section-kicker">排名變動</p>
          <h2>${report.changesComparedToPrevious.comparedTo} 之後的變化</h2>
          <p>${report.changesComparedToPrevious.summary}</p>
        </div>
      </div>
      <div class="change-list">${changeItems}</div>
    </section>

    <section class="panel animate-rise delay-3" id="sources">
      <div class="section-header">
        <div>
          <p class="section-kicker">資料來源</p>
          <h2>這份網站目前引用的主要來源</h2>
          <p>網站與自動化會優先使用官方或一手資料；無法直接驗證的項目會在晨報中明寫。</p>
        </div>
      </div>
      <div class="sources-layout">
        <article class="source-card">
          <p class="card-kicker">全站來源</p>
          <ul class="source-list">${sourceLinks}</ul>
        </article>
        <article class="source-card">
          <p class="card-kicker">網站說明</p>
          <h3>之後怎麼更新</h3>
          <p class="body-copy">
            這個網站目前讀取 <code>site/data/latest.json</code>。只要晨報自動化每天把最新結果寫進這個檔案，畫面就會自動換成最新版本。
          </p>
          <p class="body-copy">
            如果當天題材或個股排名變動，請把原因寫到 <code>changesComparedToPrevious</code>，網站首頁就會直接顯示。
          </p>
          <p class="footer-note">${report.footnote}</p>
        </article>
      </div>
    </section>
  `;

  if (discoveries.length > 0) {
    newsNavLink?.classList.remove("is-hidden");
  } else {
    newsNavLink?.classList.add("is-hidden");
  }

  syncQuickNav();
}

function renderTheme(theme, open) {
  const stocks = Array.isArray(theme.stocks) ? theme.stocks : [];
  const whyNowItems = Array.isArray(theme.whyNow) ? theme.whyNow : [];
  const stockCards = stocks.map((stock) => renderStock(theme, stock)).join("");
  const whyNow = whyNowItems
    .map(
      (item) => `
        <article class="info-block">
          <p class="info-label">${item.label}</p>
          <p class="info-text">${item.text}</p>
        </article>
      `
    )
    .join("");

  const themeRisks = (Array.isArray(theme.downsideEvents) ? theme.downsideEvents : [])
    .map((risk) => `<li>${risk}</li>`)
    .join("");
  const gateSummary = formatGateStatus(theme.gateStatus);
  const breadthSummary = formatBreadthStats(theme.breadthStats);

  return `
    <article class="theme-card">
      <details ${open ? "open" : ""}>
        <summary>
          <div class="theme-head">
            <div class="theme-title">
              <span class="rank-badge">${theme.rank}</span>
              <div>
                <h3>${theme.name}</h3>
                <p class="theme-summary">${theme.summary}</p>
              </div>
            </div>
            <div class="badge-row">
              ${theme.heat ? `<span class="heat-badge ${heatToneMap[theme.heat] || "heat-cool"}">${theme.heat}</span>` : ""}
              ${renderStateBadge(theme.state)}
              ${renderScoreBadge(theme.themeScore, "題材分數")}
              ${renderGateBadge(theme.gateStatus)}
              <span class="pill">${theme.stance}</span>
            </div>
          </div>
        </summary>
        <div class="theme-body">
          <div class="theme-meta">
            <div class="info-block">
              <p class="info-label">估值與熱度判斷</p>
              <p class="info-text">${theme.pricingView}</p>
            </div>
            <div class="info-block">
              <p class="info-label">政策與技術主軸</p>
              <p class="info-text">${theme.policyView}</p>
            </div>
          </div>
          <div class="theme-meta">
            <div class="info-block">
              <p class="info-label">Lifecycle 與 gate</p>
              <p class="info-text">${gateSummary || "這版資料沒有額外的 gate 摘要。"}</p>
            </div>
            <div class="info-block">
              <p class="info-label">廣度統計</p>
              <p class="info-text">${breadthSummary || "這版資料沒有額外的 breadth 統計。"}</p>
            </div>
          </div>
          <div class="theme-meta">${whyNow}</div>
          <div class="split-copy">
            <div class="info-block">
              <p class="info-label">還有多少溢價空間</p>
              <p class="info-text">${theme.premiumSpace}</p>
            </div>
            <div class="info-block">
              <p class="info-label">題材級風險事件</p>
              <ul class="risk-list">${themeRisks}</ul>
            </div>
          </div>
          <div class="stock-grid">${stockCards}</div>
        </div>
      </details>
    </article>
  `;
}

function renderStock(theme, stock) {
  return `
    <article class="stock-card">
      <div class="stock-header">
        <div class="stock-title-wrap">
          <div class="stock-title">
            <h4>${stock.rank}. ${stock.name}</h4>
            <span class="ticker">${stock.ticker}</span>
            <span class="chip">${theme.name}</span>
            ${renderStateBadge(stock.state)}
            ${renderScoreBadge(stock.stockScore, "股票分數")}
            ${renderGateBadge(stock.gateStatus)}
          </div>
          <p class="stock-role">${stock.role}</p>
        </div>
        <span class="pill">股價日 ${stock.priceDate}</span>
      </div>

      <div class="stock-metrics">
        <div class="metric-pill">
          <strong>${stock.close}</strong>
          <span>收盤價</span>
        </div>
        <div class="metric-pill">
          <strong>${stock.entry}</strong>
          <span>進場區間</span>
        </div>
        <div class="metric-pill">
          <strong>${stock.target}</strong>
          <span>目標價</span>
        </div>
        <div class="metric-pill">
          <strong>${stock.stop}</strong>
          <span>停損價</span>
        </div>
        <div class="metric-pill">
          <strong>${stock.pe}</strong>
          <span>PE / PB ${stock.pb}</span>
        </div>
        <div class="metric-pill">
          <strong class="${flowTone(stock.foreignFlow)}">${stock.foreignFlow}</strong>
          <span>外資 / 法人 ${stock.institutionFlow}</span>
        </div>
      </div>

      <div class="split-copy">
        <div class="info-block">
          <p class="info-label">核心理由</p>
          <p class="info-text">${stock.coreReason}</p>
        </div>
        <div class="info-block">
          <p class="info-label">為何還沒反映完</p>
          <p class="info-text">${stock.notPricedIn}</p>
        </div>
      </div>

      <div class="split-copy">
        <div class="info-block">
          <p class="info-label">目標價邏輯</p>
          <p class="info-text">${stock.targetLogic}</p>
        </div>
        <div class="info-block">
          <p class="info-label">近期催化</p>
          <ul class="checklist">${(Array.isArray(stock.catalysts) ? stock.catalysts : []).map((item) => `<li>${item}</li>`).join("")}</ul>
        </div>
      </div>

      <div class="split-copy">
        <div class="info-block">
          <p class="info-label">下跌風險</p>
          <ul class="risk-list">${(Array.isArray(stock.downside) ? stock.downside : []).map((item) => `<li>${item}</li>`).join("")}</ul>
        </div>
        <div class="info-block">
          <p class="info-label">消息依據</p>
          <ul class="inline-list">${(Array.isArray(stock.sourceRefs) ? stock.sourceRefs : []).map((item) => `<li>${item}</li>`).join("")}</ul>
        </div>
      </div>

      ${stock.alternativeRejected ? `
        <div class="info-block stock-alt">
          <p class="info-label">為何勝過最近替代選項</p>
          <p class="info-text">${stock.alternativeRejected}</p>
        </div>
      ` : ""}
    </article>
  `;
}

function renderObservationEmpty(type, text) {
  return `
    <article class="observation-card observation-empty">
      <p class="card-kicker">觀察池${type}</p>
      <h3>目前沒有可顯示資料</h3>
      <p class="body-copy">${text}</p>
    </article>
  `;
}

function syncQuickNav() {
  if (!quickNav) return;

  renameQuickNavLink("#focus", "交易池股票");
  renameQuickNavLink("#themes", "交易池題材");
  ensureQuickNavLink("#observation-stocks", "觀察池股票", "#focus");
  ensureQuickNavLink("#observation-themes", "觀察池題材", "#themes");
}

function renameQuickNavLink(href, label) {
  const link = quickNav?.querySelector(`a[href="${href}"]`);
  if (link) {
    link.textContent = label;
  }
}

function ensureQuickNavLink(href, label, afterHref) {
  if (!quickNav || quickNav.querySelector(`a[href="${href}"]`)) return;

  const link = document.createElement("a");
  link.href = href;
  link.textContent = label;

  const after = quickNav.querySelector(`a[href="${afterHref}"]`);
  if (after?.nextSibling) {
    quickNav.insertBefore(link, after.nextSibling);
    return;
  }

  if (after) {
    quickNav.appendChild(link);
    return;
  }

  quickNav.appendChild(link);
}

function formatWeekRange(weekRange = {}) {
  const start = weekRange.start || weekRange.from || "未提供";
  const end = weekRange.end || weekRange.to || "未提供";
  return `${start} 至 ${end}`;
}

function renderStateBadge(state) {
  if (!state) return "";

  return `<span class="state-badge state-${escapeHtml(String(state).toLowerCase())}">${formatStateLabel(state)}</span>`;
}

function renderScoreBadge(score, label) {
  if (score === undefined || score === null || score === "") return "";

  const normalized = Number(score);
  const display = Number.isFinite(normalized) ? `${normalized.toFixed(0)} / 100` : String(score);
  return `<span class="score-badge" title="${label}">${display}</span>`;
}

function renderGateBadge(gateStatus) {
  const summary = formatGateStatus(gateStatus);
  if (!summary) return "";

  return `<span class="gate-badge">${summary}</span>`;
}

function formatStateLabel(state) {
  const normalized = String(state).toLowerCase();
  const map = {
    seed: "Seed",
    confirmation: "Confirmation",
    expansion: "Expansion",
    late: "Late",
    breakdown: "Breakdown",
  };
  return map[normalized] || String(state);
}

function formatGateStatus(gateStatus) {
  if (!gateStatus) return "";
  if (typeof gateStatus === "string") return gateStatus;

  if (typeof gateStatus === "object") {
    if (gateStatus.summary) return gateStatus.summary;

    const parts = [];
    const passedCount = countGateItems(gateStatus.passed, gateStatus.passedCount);
    const nearMissCount = countGateItems(gateStatus.nearMiss, gateStatus.nearMissCount);
    const failedCount = countGateItems(gateStatus.failed, gateStatus.failedCount);

    if (passedCount !== null) parts.push(`通過 ${passedCount}`);
    if (nearMissCount !== null) parts.push(`差一項 ${nearMissCount}`);
    if (failedCount !== null) parts.push(`失敗 ${failedCount}`);

    return parts.join(" / ");
  }

  return String(gateStatus);
}

function countGateItems(items, fallbackCount) {
  if (Array.isArray(items)) return items.length;
  if (Number.isFinite(fallbackCount)) return fallbackCount;
  return null;
}

function formatBreadthStats(stats) {
  if (!stats) return "";
  if (typeof stats === "string") return stats;
  if (typeof stats !== "object") return String(stats);

  const parts = [];
  if (Number.isFinite(stats.checkedStocks)) parts.push(`受檢 ${stats.checkedStocks} 檔`);
  if (Number.isFinite(stats.outperformCount)) {
    const ratio = Number.isFinite(stats.outperformRatio)
      ? ` (${Math.round(stats.outperformRatio * 100)}%)`
      : "";
    parts.push(`跑贏 ${stats.outperformCount} 檔${ratio}`);
  }
  if (Number.isFinite(stats.institutionPositiveCount)) {
    parts.push(`法人正向 ${stats.institutionPositiveCount} 檔`);
  }
  if (Number.isFinite(stats.newCatalystCount)) {
    parts.push(`新催化 ${stats.newCatalystCount} 檔`);
  }

  return parts.join(" / ");
}

function toneClass(tone) {
  if (tone === "up") return "tone-up";
  if (tone === "down") return "tone-down";
  return "tone-flat";
}

function flowTone(value) {
  if (value.startsWith("+")) return "tone-up";
  if (value.startsWith("-")) return "tone-down";
  return "tone-flat";
}

function formatSignedAmount(value) {
  const number = Number(value);
  if (Number.isNaN(number)) {
    return String(value);
  }

  if (number > 0) return `+${number.toFixed(2)}`;
  if (number < 0) return number.toFixed(2);
  return "0.00";
}

function normalizeMarketRegime(regime) {
  const fallback = {
    score: "未提供",
    stance: "未提供",
    mode: "normal",
    summary: "這版資料還沒有 market regime 判斷。",
    scoreBreakdown: {},
    drivers: [],
    effectOnSelection: "",
  };

  if (!regime || typeof regime !== "object") {
    return fallback;
  }

  return {
    ...fallback,
    ...regime,
  };
}

function getTradingPoolLimits(mode) {
  const map = {
    risk_on: { themeMax: 5, themeLabel: "5", stockMax: 6, stockLabel: "6" },
    normal: { themeMax: 5, themeLabel: "5", stockMax: 6, stockLabel: "6" },
    selective: { themeMax: 4, themeLabel: "4", stockMax: 4, stockLabel: "4" },
    defensive: { themeMax: 3, themeLabel: "3", stockMax: 4, stockLabel: "4" },
    capital_preservation: { themeMax: 2, themeLabel: "2", stockMax: 2, stockLabel: "2" },
  };

  return map[mode] || map.normal;
}

function marketRegimeTone(score) {
  const numericScore = Number(score);
  if (!Number.isFinite(numericScore)) return "tone-flat";
  if (numericScore >= 65) return "tone-up";
  if (numericScore >= 45) return "tone-flat";
  return "tone-down";
}

function renderRegimeBanner(regime, limits) {
  if (!["defensive", "capital_preservation"].includes(regime.mode)) {
    return "";
  }

  return `
    <section class="panel regime-banner animate-rise delay-1" id="market-regime">
      <div class="section-header">
        <div>
          <p class="section-kicker">市場 Regime 提示</p>
          <h2>${regime.stance}：交易池已縮到 ${limits.themeLabel} 個題材 / ${limits.stockLabel} 檔股票</h2>
          <p>${regime.effectOnSelection || regime.summary}</p>
        </div>
      </div>
    </section>
  `;
}

initReadingMode();
loadReport();
