import {
  escapeHtml,
  formatNumber,
  getNewDiscoveries,
  loadLatestReport,
} from "./report-utils.js";

const app = document.getElementById("app");
const newsNavLink = document.getElementById("news-nav-link");

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
  const foreignFlowDisplay = formatSignedAmount(report.marketSnapshot.foreignFlowTwdBn);
  const foreignFlowTone = flowTone(foreignFlowDisplay);
  const themeCards = report.themes
    .map((theme, index) => renderTheme(theme, index === 0))
    .join("");

  const focusCards = report.topPicks
    .map(
      (pick, index) => `
        <article class="focus-card animate-rise delay-${Math.min(index, 3)}">
          <p class="card-kicker">跨題材先看</p>
          <div class="focus-title">
            <h3>${pick.rank}. ${pick.name}</h3>
            <span class="ticker">${pick.ticker}</span>
            <span class="chip">${pick.theme}</span>
          </div>
          <p class="focus-note">${pick.reason}</p>
        </article>
      `
    )
    .join("");

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
            <span class="pill">操作週 ${report.weekRange.from} 至 ${report.weekRange.to}</span>
            <span class="pill">股價基準 ${report.priceDate}</span>
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
          <article class="metric-card">
            <p class="metric-label">閱讀模式</p>
            <p class="metric-value">手機優先</p>
            <p class="metric-note">短段落、單層條列、少用寬表格</p>
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

    <section class="panel animate-rise delay-1" id="focus">
      <div class="section-header">
        <div>
          <p class="section-kicker">今天先看</p>
          <h2>跨題材最值得先追蹤的名單</h2>
          <p>這裡先放網站首頁最值得看的幾檔，方便在手機上先掃一輪。</p>
        </div>
      </div>
      <div class="focus-grid">${focusCards}</div>
    </section>

    <section class="panel animate-rise delay-2" id="themes">
      <div class="section-header">
        <div>
          <p class="section-kicker">五大題材</p>
          <h2>按本週可操作性排序</h2>
          <p>每個題材都會先說熱度、技術、原料、政策與溢價空間，再往下拆五檔個股。</p>
        </div>
      </div>
      <div class="theme-accordion">${themeCards}</div>
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
}

function renderTheme(theme, open) {
  const stockCards = theme.stocks.map((stock) => renderStock(theme, stock)).join("");
  const whyNow = theme.whyNow
    .map(
      (item) => `
        <article class="info-block">
          <p class="info-label">${item.label}</p>
          <p class="info-text">${item.text}</p>
        </article>
      `
    )
    .join("");

  const themeRisks = theme.downsideEvents.map((risk) => `<li>${risk}</li>`).join("");

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
              <span class="heat-badge ${heatToneMap[theme.heat] || "heat-cool"}">${theme.heat}</span>
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
          <ul class="checklist">${stock.catalysts.map((item) => `<li>${item}</li>`).join("")}</ul>
        </div>
      </div>

      <div class="split-copy">
        <div class="info-block">
          <p class="info-label">下跌風險</p>
          <ul class="risk-list">${stock.downside.map((item) => `<li>${item}</li>`).join("")}</ul>
        </div>
        <div class="info-block">
          <p class="info-label">消息依據</p>
          <ul class="inline-list">${stock.sourceRefs.map((item) => `<li>${item}</li>`).join("")}</ul>
        </div>
      </div>
    </article>
  `;
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

loadReport();
