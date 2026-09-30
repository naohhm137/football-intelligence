import { renderOddsTimeline } from "./odds-chart.js";

const ACTION_LABELS = {
  NO_BET_UNVALIDATED: "暂不投注：模型尚未通过前瞻验证",
  NO_BET_NO_LIVE_ODDS: "暂不投注：没有取得真实亚盘",
  NO_BET_INSUFFICIENT_MARKET: "暂不投注：盘口样本不足",
};
const MISSING_LABELS = {
  weather: "比赛地天气",
  news: "场外新闻",
  team_context: "近期战绩与伤停",
  odds: "亚盘与水位",
};
const PROBABILITY_LABELS = { home: "主胜", draw: "平局", away: "客胜" };
const ASIAN_LABELS = {
  full_loss: "全输", half_loss: "半输", push: "走水", half_win: "半赢", full_win: "全赢",
};

function percent(value) {
  return Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(1)}%` : "—";
}

function safeEvidence(items) {
  return (items ?? []).filter((item) => {
    try {
      return ["http:", "https:"].includes(new URL(item.url).protocol);
    } catch {
      return false;
    }
  });
}

export function buildResultViewModel(report) {
  const quantitative = report.quantitative ?? {};
  const probabilities = quantitative.result_probabilities ?? {};
  return {
    fixture: report.fixture,
    actionLabel: ACTION_LABELS[report.action] ?? "暂不投注：证据不足",
    validated: quantitative.validated_for_betting === true,
    probabilityBasis: quantitative.probability_basis,
    probabilities: ["home", "draw", "away"].map((id) => ({
      id, label: PROBABILITY_LABELS[id], percent: percent(probabilities[id]), value: probabilities[id] ?? 0,
    })),
    asianStates: Object.entries(quantitative.asian_state_probabilities ?? {}).map(([id, value]) => ({
      id, label: ASIAN_LABELS[id] ?? id, percent: percent(value), value,
    })),
    asianLine: quantitative.asian_line,
    asianEv: quantitative.asian_ev,
    direction: quantitative.relative_direction,
    completeness: percent(report.data_completeness),
    missing: (report.missing_sources ?? []).map((id) => MISSING_LABELS[id] ?? id),
    evidence: safeEvidence(report.evidence),
    odds: report.odds ?? [],
    explanation: report.ai_explanation,
  };
}

function element(name, className, text) {
  const node = document.createElement(name);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function probabilityBlock(probabilities) {
  const block = element("div", "probability-grid");
  probabilities.forEach((item) => {
    const row = element("div", "probability-item");
    row.append(element("span", "probability-label", item.label), element("strong", "probability-value", item.percent));
    block.append(row);
  });
  return block;
}

function factorList(title, items) {
  const section = element("section", "factor-group");
  section.append(element("h4", "", title));
  const list = element("ul", "factor-list");
  if (!items?.length) list.append(element("li", "muted", "没有可核验内容"));
  else items.forEach((item) => list.append(element("li", "", item)));
  section.append(list);
  return section;
}

let activeAnimations = [];
function reveal(section) {
  activeAnimations.forEach((animation) => animation.cancel());
  activeAnimations = [];
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  section.querySelectorAll("[data-reveal]").forEach((node, index) => {
    activeAnimations.push(node.animate(
      [
        { opacity: 0, transform: "translateY(10px)" },
        { opacity: 1, transform: "translateY(0)" },
      ],
      { duration: 240, delay: index * 70, easing: "cubic-bezier(0.23, 1, 0.32, 1)", fill: "both" },
    ));
  });
}

export function renderAnalysis(report) {
  const view = buildResultViewModel(report);
  const section = document.querySelector("#analysis-result");
  const fixture = document.querySelector("#fixture-identity");
  fixture.replaceChildren();
  fixture.append(
    element("p", "fixture-meta", `${view.fixture.competition} · ${new Date(view.fixture.kickoff_utc).toLocaleString("zh-CN")}`),
    element("h2", "fixture-title", `${view.fixture.home_team}  对  ${view.fixture.away_team}`),
  );

  const validation = document.querySelector("#validation-status");
  validation.dataset.validated = String(view.validated);
  validation.textContent = view.actionLabel;

  const summary = document.querySelector("#result-summary");
  summary.replaceChildren(
    element("p", "model-label", "1X2 研究概率 · 尚未校准为盈利概率"),
    probabilityBlock(view.probabilities),
  );

  const asian = document.querySelector("#asian-summary");
  asian.replaceChildren();
  if (!view.asianStates.length) {
    asian.append(element("p", "empty-state", "没有取得足够的真实亚盘快照，因此不计算亚盘 EV。"));
  } else {
    const headline = element("p", "asian-headline");
    const direction = view.direction === "home" ? "主队方向" : "客队方向";
    headline.textContent = `盘口 ${view.asianLine} · ${direction} · 研究 EV ${(view.asianEv * 100).toFixed(1)}%`;
    asian.append(headline, probabilityBlock(view.asianStates));
  }

  const explanation = view.explanation;
  document.querySelector("#ai-summary").textContent = explanation?.summary || "AI解释暂时不可用，量化结果仍按原始证据显示。";
  const factors = document.querySelector("#factor-groups");
  factors.replaceChildren(
    factorList("支持因素", explanation?.supporting_factors),
    factorList("反向因素", explanation?.opposing_factors),
    factorList("风险提示", explanation?.risk_notes),
  );

  const missing = document.querySelector("#missing-data");
  missing.replaceChildren();
  if (view.missing.length) view.missing.forEach((item) => missing.append(element("li", "", item)));
  else missing.append(element("li", "complete", "本轮计划数据均已取得"));

  const evidence = document.querySelector("#evidence-list");
  evidence.replaceChildren();
  if (!view.evidence.length) evidence.append(element("li", "empty-state", "本轮没有可公开引用的外部证据。"));
  view.evidence.forEach((item) => {
    const link = element("a", "evidence-link", item.title);
    link.href = item.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    const meta = element("span", "evidence-meta", item.publisher || "来源");
    const row = element("li", "evidence-item");
    row.append(link, meta);
    evidence.append(row);
  });

  const oddsFigure = document.querySelector("#odds-figure");
  oddsFigure.hidden = !renderOddsTimeline(document.querySelector("#odds-timeline"), view.odds);
  section.hidden = false;
  reveal(section);
  section.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
}

if (typeof window !== "undefined") {
  window.addEventListener("analysis:complete", (event) => renderAnalysis(event.detail));
}
