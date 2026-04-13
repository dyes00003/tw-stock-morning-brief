import {
  escapeHtml,
  getNewDiscoveries,
  loadLatestReport,
} from "./report-utils.js";

const app = document.getElementById("news-app");

async function loadNewsPage() {
  try {
    const report = await loadLatestReport();
    render(report);
  } catch (error) {
    app.innerHTML = `
      <section class="loading-card">
        <p class="loading-kicker">載入失敗</p>
        <h2>這次新消息頁面還沒準備好</h2>
        <p>請確認 <code>site/data/latest.json</code> 是否存在，或稍後重新整理。</p>
        <p class="meta-note">${escapeHtml(String(error))}</p>
      </section>
    `;
  }
}

function render(report) {
  const discoveries = getNewDiscoveries(report);
  const discoveryCards = discoveries
    .map(
      (item) => `
        <article class="discovery-card discovery-card-strong">
          <p class="card-kicker">${item.scope}</p>
          <h3>${item.title}</h3>
          <p class="body-copy">${item.detail}</p>
          <div class="info-block discovery-impact">
            <p class="info-label">為什麼這條值得看</p>
            <p class="info-text">${item.whyItMatters}</p>
          </div>
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

  app.innerHTML = `
    <section class="panel overview animate-rise" id="latest">
      <div class="panel-grid">
        <div class="section-header">
          <div>
            <p class="section-kicker">這次更新</p>
            <h2>${report.headline}</h2>
            <p>${report.deck}</p>
          </div>
          <div class="badge-row">
            <span class="pill">報告日 ${report.reportDate}</span>
            <span class="pill">股價基準 ${report.priceDate}</span>
          </div>
        </div>
        ${
          discoveries.length
            ? `
              <div class="discovery-grid">
                ${discoveryCards}
              </div>
            `
            : `
              <article class="loading-card compact-card">
                <p class="loading-kicker">這次沒有新增</p>
                <h2>這次更新沒有新抓到可獨立列示的新聞或資訊</h2>
                <p>像重跑、資料映射、排名沒變、生成 log 這些流程更新都不算，首頁也會自動隱藏「新消息」入口。</p>
              </article>
            `
        }
      </div>
    </section>

    <section class="panel animate-rise delay-1" id="sources">
      <div class="section-header">
        <div>
          <p class="section-kicker">來源</p>
          <h2>這次新消息仍對應到同一份晨報來源池</h2>
          <p>頁面只負責濃縮本次新抓到的新聞或資訊；原始引用仍以首頁晨報與最新資料檔為準。</p>
        </div>
      </div>
      <article class="source-card">
        <p class="card-kicker">全站來源</p>
        <ul class="source-list">${sourceLinks}</ul>
      </article>
    </section>
  `;
}

loadNewsPage();
