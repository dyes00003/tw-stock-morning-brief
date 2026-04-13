const proceduralDiscoveryPattern =
  /排名仍不變|名單不變|新增.*log|log 檔|同步網站|已推送|初始化|無變動/;

export async function loadLatestReport(dataPath = "./data/latest.json") {
  const response = await fetch(dataPath);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  return response.json();
}

export function formatNumber(value) {
  return new Intl.NumberFormat("zh-TW").format(value);
}

export function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

export function getNewDiscoveries(report) {
  if (Array.isArray(report?.newDiscoveries) && report.newDiscoveries.length > 0) {
    return report.newDiscoveries.map((item, index) =>
      normalizeDiscovery(item, index, report?.changesComparedToPrevious?.summary || "")
    );
  }

  const items = report?.changesComparedToPrevious?.items || [];
  return items
    .filter((item) => isMeaningfulDiscovery(item))
    .map((item, index) =>
      normalizeDiscovery(
        {
          title: item.title,
          detail: item.reason,
          scope: "本次更新",
          whyItMatters: report?.changesComparedToPrevious?.summary || "",
        },
        index,
        report?.changesComparedToPrevious?.summary || ""
      )
    );
}

function normalizeDiscovery(item, index, fallbackWhy) {
  return {
    id: item.id || `discovery-${index + 1}`,
    title: item.title || `新發現 ${index + 1}`,
    detail: item.detail || item.reason || "這次更新沒有留下更多細節。",
    scope: item.scope || "本次更新",
    whyItMatters: item.whyItMatters || fallbackWhy || "這則消息會影響這次晨報的排序與選股判斷。",
  };
}

function isMeaningfulDiscovery(item) {
  const title = item?.title || "";
  const reason = item?.reason || "";
  return !proceduralDiscoveryPattern.test(`${title} ${reason}`);
}
