const SVG_NS = "http://www.w3.org/2000/svg";
const COLORS = ["#f6be57", "#72c7e7", "#76d19b", "#e48670", "#c9a8ff"];

export function buildOddsSeries(snapshots) {
  const usable = snapshots
    .filter((item) => item.bookmaker && item.captured_at)
    .map((item) => ({
      bookmaker: item.bookmaker,
      captured_at: item.captured_at,
      timestamp: Date.parse(item.captured_at),
      line: Number(item.line),
      home_price: Number(item.home_price),
      away_price: Number(item.away_price),
    }))
    .filter((item) => Number.isFinite(item.timestamp) && Number.isFinite(item.line))
    .sort((left, right) => left.timestamp - right.timestamp);

  const series = {};
  for (const item of usable) {
    (series[item.bookmaker] ??= []).push(item);
  }
  return {
    start: usable[0]?.captured_at ?? null,
    end: usable.at(-1)?.captured_at ?? null,
    series,
  };
}

function svgElement(name, attributes = {}) {
  const element = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attributes)) {
    element.setAttribute(key, value);
  }
  return element;
}

function scale(value, min, max, start, end) {
  if (min === max) return (start + end) / 2;
  return start + ((value - min) / (max - min)) * (end - start);
}

export function renderOddsTimeline(svg, snapshots) {
  svg.replaceChildren();
  const data = buildOddsSeries(snapshots);
  const all = Object.values(data.series).flat();
  if (!all.length) {
    svg.setAttribute("aria-label", "没有可绘制的真实赔率快照");
    return false;
  }

  const width = 760;
  const height = 300;
  const left = 56;
  const right = 24;
  const start = Math.min(...all.map((item) => item.timestamp));
  const end = Math.max(...all.map((item) => item.timestamp));
  const lines = all.map((item) => item.line);
  const prices = all.map((item) => item.home_price).filter(Number.isFinite);
  const lineMin = Math.min(...lines);
  const lineMax = Math.max(...lines);
  const priceMin = prices.length ? Math.min(...prices) : 1.8;
  const priceMax = prices.length ? Math.max(...prices) : 2.0;

  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("aria-label", "各公司真实亚盘盘口与主队水位时间线");

  const labels = [
    ["盘口", 26],
    ["主队水位", 165],
  ];
  for (const [label, y] of labels) {
    const text = svgElement("text", { x: 4, y, class: "chart-axis-label" });
    text.textContent = label;
    svg.append(text);
  }
  svg.append(
    svgElement("line", { x1: left, y1: 132, x2: width - right, y2: 132, class: "chart-divider" }),
  );

  Object.entries(data.series).forEach(([bookmaker, points], index) => {
    const color = COLORS[index % COLORS.length];
    const xFor = (point) => scale(point.timestamp, start, end, left, width - right);
    const linePoints = points.map((point) => `${xFor(point)},${scale(point.line, lineMin, lineMax, 104, 40)}`).join(" ");
    const pricePoints = points
      .filter((point) => Number.isFinite(point.home_price))
      .map((point) => `${xFor(point)},${scale(point.home_price, priceMin, priceMax, 266, 176)}`)
      .join(" ");

    if (points.length > 1) {
      svg.append(svgElement("polyline", { points: linePoints, fill: "none", stroke: color, class: "chart-line" }));
      if (pricePoints.includes(" ")) {
        svg.append(svgElement("polyline", { points: pricePoints, fill: "none", stroke: color, class: "chart-price" }));
      }
    }
    points.forEach((point) => {
      svg.append(svgElement("circle", {
        cx: xFor(point), cy: scale(point.line, lineMin, lineMax, 104, 40), r: 4, fill: color,
      }));
      if (Number.isFinite(point.home_price)) {
        svg.append(svgElement("circle", {
          cx: xFor(point), cy: scale(point.home_price, priceMin, priceMax, 266, 176), r: 4, fill: color,
        }));
      }
    });

    const legend = svgElement("text", { x: left + index * 132, y: 294, fill: color, class: "chart-legend" });
    legend.textContent = bookmaker;
    svg.append(legend);
  });
  return true;
}
