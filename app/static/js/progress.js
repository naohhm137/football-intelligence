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
  return SOURCES.map((source) => ({
    ...source,
    state: missing.has(source.id) ? "missing" : "success",
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
      return item;
    }),
  );
}

export function setProgressActive(section, active) {
  section.hidden = false;
  section.dataset.active = String(active);
}
