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
  if (!Array.isArray(report?.newDiscoveries)) {
    return [];
  }

  return report.newDiscoveries.map((item, index) =>
    normalizeDiscovery(item, index, report?.changesComparedToPrevious?.summary || "")
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
