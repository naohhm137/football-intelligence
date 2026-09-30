import { AnalysisApiError, getServiceHealth, submitMatch } from "./api.js";
import {
  loadingSourceStates,
  renderSourceProgress,
  setProgressActive,
  sourceStatesFromReport,
} from "./progress.js";

export function createAnalysisRunner({ submit = submitMatch, onActiveChange = () => {} } = {}) {
  let activeController = null;

  return {
    async run(query) {
      activeController?.abort();
      const controller = new AbortController();
      activeController = controller;
      onActiveChange(true);
      try {
        return await submit(query, { signal: controller.signal });
      } finally {
        if (activeController === controller) {
          activeController = null;
          onActiveChange(false);
        }
      }
    },
    cancel() {
      activeController?.abort();
    },
  };
}

const ERROR_TEXT = {
  FIXTURE_NOT_FOUND: "没有找到对应比赛。请检查正式队名和开赛时间。",
  INVALID_REQUEST: "请填写不同的主客队和有效的开赛时间。",
  ANALYSIS_FAILED: "实时分析暂时失败，已停止本次扫描，请稍后重试。",
  SERVICE_UNAVAILABLE: "数据服务暂时离线，请稍后重试。",
};

function queryFromForm(form) {
  return {
    home_team: form.elements.home_team.value,
    away_team: form.elements.away_team.value,
    kickoff_local: form.elements.kickoff_local.value,
  };
}

function toLocalInputValue(isoTimestamp) {
  const value = new Date(isoTimestamp);
  const local = new Date(value.getTime() - value.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function renderFixtureCandidates(container, candidates, form) {
  container.replaceChildren();
  if (!candidates.length) return;

  const heading = document.createElement("p");
  heading.textContent = "找到几场相似比赛，请确认：";
  const list = document.createElement("div");
  list.className = "candidate-list";

  candidates.forEach((candidate, index) => {
    const label = document.createElement("label");
    label.className = "candidate-option";
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "fixture_candidate";
    radio.value = String(index);
    const text = document.createElement("span");
    const kickoff = new Date(candidate.kickoff_utc).toLocaleString("zh-CN", {
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
    text.textContent = `${candidate.home_team} 对 ${candidate.away_team} · ${candidate.competition} · ${kickoff}`;
    radio.addEventListener("change", () => {
      form.elements.home_team.value = candidate.home_team;
      form.elements.away_team.value = candidate.away_team;
      form.elements.kickoff_local.value = toLocalInputValue(candidate.kickoff_utc);
    });
    label.append(radio, text);
    list.append(label);
  });
  container.append(heading, list);
}

function boot() {
  const form = document.querySelector("#match-search form");
  const submitButton = form.querySelector('button[type="submit"]');
  const message = document.querySelector("#form-message");
  const candidates = document.querySelector("#fixture-candidates");
  const progress = document.querySelector("#research-progress");
  const sourceList = document.querySelector("#source-list");
  const resultSection = document.querySelector("#analysis-result");
  const serviceState = document.querySelector("#service-state");

  const runner = createAnalysisRunner({
    onActiveChange(active) {
      submitButton.disabled = active;
      submitButton.querySelector("span").textContent = active ? "正在扫描" : "开始情报扫描";
      setProgressActive(progress, active);
    },
  });

  getServiceHealth()
    .then((health) => {
      serviceState.dataset.state = "online";
      serviceState.textContent = health.ai_configured ? "数据与 AI 已连接" : "数据服务已连接";
    })
    .catch(() => {
      serviceState.dataset.state = "offline";
      serviceState.textContent = "数据服务暂时离线";
    });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    message.textContent = "";
    candidates.replaceChildren();

    if (!form.reportValidity()) return;
    renderSourceProgress(sourceList, loadingSourceStates());
    resultSection.hidden = true;

    try {
      const report = await runner.run(queryFromForm(form));
      renderSourceProgress(sourceList, sourceStatesFromReport(report));
      window.dispatchEvent(new CustomEvent("analysis:complete", { detail: report }));
    } catch (error) {
      if (error.name === "AbortError") return;
      renderSourceProgress(
        sourceList,
        loadingSourceStates().map((source) => ({ ...source, state: "error" })),
      );
      if (error instanceof AnalysisApiError && error.code === "AMBIGUOUS_FIXTURE") {
        message.textContent = error.message;
        renderFixtureCandidates(candidates, error.candidates, form);
        return;
      }
      message.textContent = ERROR_TEXT[error.code] || error.message || "分析暂时失败，请稍后重试。";
    }
  });
}

if (typeof document !== "undefined") {
  boot();
}
