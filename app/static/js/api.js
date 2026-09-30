export class AnalysisApiError extends Error {
  constructor(message, { code = "ANALYSIS_FAILED", status = 0, candidates = [] } = {}) {
    super(message);
    this.name = "AnalysisApiError";
    this.code = code;
    this.status = status;
    this.candidates = candidates;
  }
}

function publicPayload(query) {
  const kickoff = new Date(query.kickoff_local);
  if (Number.isNaN(kickoff.getTime())) {
    throw new AnalysisApiError("请输入有效的开赛时间。", { code: "INVALID_REQUEST" });
  }

  return {
    home_team: String(query.home_team ?? "").trim(),
    away_team: String(query.away_team ?? "").trim(),
    kickoff_local: kickoff.toISOString(),
  };
}

export async function submitMatch(query, { fetchImpl = fetch, signal } = {}) {
  const response = await fetchImpl("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(publicPayload(query)),
    signal,
  });
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new AnalysisApiError(
      payload.error?.message || "分析暂时失败，请稍后重试。",
      {
        code: payload.error?.code,
        status: response.status,
        candidates: Array.isArray(payload.candidates) ? payload.candidates : [],
      },
    );
  }

  return payload;
}

export async function getServiceHealth({ fetchImpl = fetch, signal } = {}) {
  const response = await fetchImpl("/api/health", { signal });
  if (!response.ok) {
    throw new AnalysisApiError("数据服务暂时不可用。", {
      code: "SERVICE_UNAVAILABLE",
      status: response.status,
    });
  }
  return response.json();
}
