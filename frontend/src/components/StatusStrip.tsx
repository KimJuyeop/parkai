import { PRESETS, ago, handledHere } from "../lib/domain";
import { useCfg } from "../state/AppState";

function loadColor(p: number) {
  return p >= 85 ? "var(--bad)" : p >= 70 ? "var(--warn)" : "var(--accent)";
}

/** 모니터링 맨 위 상태 줄: 판정 · CCTV · 사이클 · CPU · 메모리 · 서버 전송 */
export function StatusStrip() {
  const { cfg, status, alive, system, cycleHistory } = useCfg();
  const mine = cfg.cameras.filter((c) => handledHere(cfg, c));
  const offline = alive ? mine.filter((c) => status.cameras[c.ip]?.status === "no_response").length : 0;
  const preset = PRESETS.find((p) => p.id === cfg.detection.preset)?.name ?? "";
  const res = system?.resources;
  const cpu = res?.cpu_percent;
  const mem = res?.memory;
  const memPct = mem ? Math.round((mem.used_mb / mem.total_mb) * 100) : null;
  const disk = res?.storage;
  const hist = cycleHistory.length ? cycleHistory : [];
  // 그래프 막대 높이 기준 (짧은 사이클이 너무 커 보이지 않도록 최소 1초). 표시하는 최대값과는 다르다
  const scale = Math.max(1, ...hist);
  const max = hist.length ? Math.max(...hist) : null;
  const avg = hist.length ? hist.reduce((a, b) => a + b, 0) / hist.length : null;
  const gb = (mb: number) => (mb / 1024).toFixed(1);

  return (
    <section className="stats" aria-label="보드 상태">
      <div className="stat">
        <span className="meta">판정</span>
        <span className="stat__value"><span className={`dot ${alive ? "dot--ok" : "dot--bad"}`} />{alive ? "동작 중" : "정지"}</span>
        <span className="meta">{alive ? preset : "워커가 실행 중이 아닙니다"}</span>
      </div>
      <div className="stat">
        <span className="meta">CCTV</span>
        <span className="stat__value mono">{alive ? mine.length - offline : "-"}<span className="stat__unit">&nbsp;/ {mine.length}대</span></span>
        <span className="meta" style={{ color: offline ? "var(--bad)" : undefined }}>
          {!alive ? "판정 정지 중" : offline ? `응답 없음 ${offline}대` : "모두 연결됨"}
        </span>
      </div>
      <div className="stat">
        <span className="meta">사이클</span>
        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 8 }}>
          <span className="stat__value mono">
            {alive && status.cycle_sec != null ? status.cycle_sec.toFixed(1) : "-"}<span className="stat__unit">초</span>
          </span>
          <div className="spark" aria-hidden="true">
            {hist.map((v, i) => (
              <span key={i} className="spark__bar" style={{ height: `${Math.round((v / scale) * 100)}%`, background: i === hist.length - 1 ? "var(--accent)" : undefined }} />
            ))}
          </div>
        </div>
        <span className="meta mono">{avg != null && max != null ? `평균 ${avg.toFixed(1)} · 최대 ${max.toFixed(1)}` : "기록 없음"}</span>
      </div>
      <div className="stat">
        <span className="meta">CPU</span>
        <span className="stat__value mono">{cpu ?? "-"}<span className="stat__unit">%</span></span>
        <div className="meter" role="meter" aria-label="CPU 사용률" aria-valuenow={cpu ?? 0} aria-valuemin={0} aria-valuemax={100}>
          <div className="meter__fill" style={{ width: `${cpu ?? 0}%`, background: loadColor(cpu ?? 0) }} />
        </div>
        <span className="meta">{res?.temperature_c != null ? `온도 ${res.temperature_c}°C` : "온도 -"}</span>
      </div>
      <div className="stat">
        <span className="meta">메모리</span>
        <span className="stat__value mono">{mem ? gb(mem.used_mb) : "-"}<span className="stat__unit">&nbsp;/ {mem ? gb(mem.total_mb) : "-"}GB</span></span>
        <div className="meter" role="meter" aria-label="메모리 사용률" aria-valuenow={memPct ?? 0} aria-valuemin={0} aria-valuemax={100}>
          <div className="meter__fill" style={{ width: `${memPct ?? 0}%`, background: loadColor(memPct ?? 0) }} />
        </div>
        <span className="meta">{disk ? `저장공간 ${gb(disk.used_mb)} / ${gb(disk.total_mb)}GB` : "저장공간 -"}</span>
      </div>
      <div className="stat">
        <span className="meta">서버 전송</span>
        {!cfg.server.enabled ? (
          <><span className="stat__value"><span className="dot" />사용 안 함</span><span className="meta">시스템 설정에서 켭니다</span></>
        ) : (
          <>
            <span className="stat__value"><span className={`dot ${status.server_error ? "dot--bad" : "dot--ok"}`} />{status.server_error ? "오류" : "정상"}</span>
            <span className="meta" title={status.server_error ?? undefined} style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {status.server_error ?? (alive ? `${ago(status.updated_at)} 전송` : "-")}
            </span>
          </>
        )}
      </div>
    </section>
  );
}
