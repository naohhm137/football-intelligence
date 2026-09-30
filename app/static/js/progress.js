const SOURCES = [
  { id: "fixture", label: "赛程身份" },
  { id: "team_context", label: "近期战绩与伤停" },
  { id: "weather", label: "比赛地天气" },
  { id: "odds", label: "亚盘与水位" },
  { id: "news", label: "场外新闻" },
];

export function loadingSourceStates() {
  return SOURCES.map((source) => ({ ...source, state: "loading" }));
}

export function sourceStatesFromReport(report) {
  const missing = new Set(report.missing_sources ?? []);
  const statuses = new Map((report.source_statuses ?? []).map((item) => [item.source, item]));
  return SOURCES.map((source) => ({
    ...source,
    state: statuses.get(source.id)?.status === "error"
      ? "error"
      : (missing.has(source.id) ? "missing" : "success"),
    detail: statuses.get(source.id)?.last_success_at
      ? `上次成功 ${new Date(statuses.get(source.id).last_success_at).toLocaleString("zh-CN")}`
      : "",
  }));
}

const STATE_TEXT = {
  waiting: "等待",
  loading: "采集中",
  success: "已核验",
  missing: "暂无数据",
  error: "采集失败",
};

export function renderSourceProgress(container, states) {
  container.replaceChildren(
    ...states.map((source) => {
      const item = document.createElement("li");
      item.className = "source-item";
      item.dataset.state = source.state;

      const label = document.createElement("span");
      label.textContent = source.label;
      const state = document.createElement("span");
      state.className = "source-state";
      state.textContent = STATE_TEXT[source.state] ?? source.state;
      item.append(label, state);
      if (source.detail) {
        const detail = document.createElement("small");
        detail.className = "source-detail";
        detail.textContent = source.detail;
        item.append(detail);
      }
      return item;
    }),
  );
}

export function setProgressActive(section, active) {
  section.hidden = false;
  section.dataset.active = String(active);
}
