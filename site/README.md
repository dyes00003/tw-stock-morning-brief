# 台股晨報看板

這是一個不靠任何前端框架的靜態網站，專門把每天的台股題材晨報整理成手機優先的閱讀格式。

## 本機預覽

在 `site/` 目錄下執行：

```bash
python3 -m http.server 4173
```

然後打開：

```text
http://localhost:4173
```

## 目前資料來源

網站讀取 `data/latest.json`。只要把晨報自動化的結果寫進這個檔案，網站重新整理後就會顯示最新內容。

## 建議的自動化方式

每個工作天早上 08:00：

1. 重新抓最新美國宏觀、台灣政策、TWSE / TPEX / MOPS 與公司訊息。
2. 產出 thread 版手機晨報。
3. 同步覆寫 `site/data/latest.json`。
4. 若題材或個股排名與前一天不同，把原因寫進 `changesComparedToPrevious`。
