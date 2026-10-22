import { useRef, useState, type ChangeEvent } from "react";
import { api } from "../api/client";
import type { AppConfig, CameraProfile, Preset, ServerTestResult } from "../api/types";
import { FULL_LAMP, INDICATOR_COLORS, PRESETS } from "../lib/domain";
import { useCfg } from "../state/AppState";
import { Check, Field, TextInput } from "../components/ui";
import { Icon } from "../components/Icon";

// 시스템 설정 화면과 모니터링 빠른 설정 패널이 같이 쓰는 설정 묶음. compact 는 패널용(한 줄씩).

type P = { compact?: boolean };
const num = (v: string) => Number(v);

export function BasicFields({ compact }: P) {
  const { cfg, edit } = useCfg();
  return (
    <div className={`form-grid${compact ? " form-grid--2" : ""}`}>
      <Field label="현장명" className={compact ? "span-2" : ""}>
        <TextInput value={cfg.site.name} onCommit={(v) => edit((d) => { d.site.name = v; }, "현장명 변경")} />
      </Field>
      <Field label="보드명">
        <TextInput value={cfg.site.board_name} onCommit={(v) => edit((d) => { d.site.board_name = v; }, "보드명 변경")} />
      </Field>
      {!compact && (
        <Field label="전송용 보드 IP">
          <TextInput mono value={cfg.network.board_ip ?? ""} placeholder="자동"
            onCommit={(v) => edit((d) => { d.network.board_ip = v.trim() || null; }, "보드 IP 변경")} />
        </Field>
      )}
      <Field label="판정 주기 (초)">
        <TextInput mono type="number" step="1" value={cfg.runtime.cycle_target_sec}
          onCommit={(v) => edit((d) => { d.runtime.cycle_target_sec = num(v); }, "판정 주기 변경")} />
      </Field>
    </div>
  );
}

export function ServerFields({ compact }: P) {
  const { cfg, edit, changes, toast } = useCfg();
  const [result, setResult] = useState<ServerTestResult | null>(null);
  const [busy, setBusy] = useState(false);
  const test = async () => {
    if (changes > 0) return toast("먼저 저장하세요. 전송 테스트는 저장된 설정으로 보냅니다");
    setBusy(true);
    try {
      setResult(await api.serverTest());
    } catch (e) {
      setResult({ url: "", error: (e as Error).message, payload: null });
    } finally {
      setBusy(false);
    }
  };
  const ok = result && !result.error && (result.status_code ?? 0) < 400;
  return (
    <>
      <Check label="전송 사용" checked={cfg.server.enabled} onChange={(v) => edit((d) => { d.server.enabled = v; }, v ? "서버 전송 켬" : "서버 전송 끔")} />
      <div className={`form-grid${compact ? " form-grid--2" : ""}`}>
        <Field label="서버 주소" className="span-2">
          <TextInput mono value={cfg.server.base_url} placeholder="http://192.168.0.197:8000"
            onCommit={(v) => edit((d) => { d.server.base_url = v.trim(); }, "서버 주소 변경")} />
        </Field>
        <Field label="경로" className={compact ? "span-2" : ""}>
          <TextInput mono value={cfg.server.path} onCommit={(v) => edit((d) => { d.server.path = v.trim(); }, "전송 경로 변경")} />
        </Field>
        {!compact && (
          <Field label="응답 대기 (초)">
            <TextInput mono type="number" step="0.5" value={cfg.server.timeout_sec}
              onCommit={(v) => edit((d) => { d.server.timeout_sec = num(v); }, "응답 대기 변경")} />
          </Field>
        )}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
        <button type="button" className="btn" onClick={test} disabled={busy}>{busy ? "보내는 중…" : "전송 테스트"}</button>
        {result && (
          <span className="meta" style={{ color: ok ? "var(--free)" : "var(--bad)" }}>
            {result.error ? `실패: ${result.error}` : `응답 ${result.status_code}`}
          </span>
        )}
      </div>
      {result && !compact && (
        <pre className="mono" style={{ margin: 0, padding: 10, borderRadius: 8, background: "var(--surface-2)", fontSize: 12, maxHeight: 200, overflow: "auto", whiteSpace: "pre-wrap" }}>
          {result.body ? `${result.body}\n\n` : ""}보낸 내용:{"\n"}{JSON.stringify(result.payload, null, 2)}
        </pre>
      )}
    </>
  );
}

export function JudgeFields({ compact }: P) {
  const { cfg, edit } = useCfg();
  const det = cfg.detection;
  const car = det.classes.car ?? { enabled: true, conf: 0.45 };
  return (
    <>
      <div role="radiogroup" aria-label="판정 방식" style={{ display: "grid", gap: 6, gridTemplateColumns: compact ? "1fr" : "repeat(auto-fit, minmax(220px, 1fr))" }}>
        {PRESETS.map((p) => (
          <button key={p.id} type="button" role="radio" aria-checked={det.preset === p.id} className="preset"
            onClick={() => det.preset !== p.id && edit((d) => { d.detection.preset = p.id as Preset; }, `판정 방식 → ${p.name}`)}>
            <span className="preset__radio" />
            <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <span className="preset__name">{p.name}</span>
              <span className="meta">{p.desc}</span>
              {!compact && <span className="meta mono">{p.tag}</span>}
            </span>
          </button>
        ))}
      </div>
      {det.preset === "custom" && !compact && (
        <div className="form-grid" style={{ padding: 14, borderRadius: 10, background: "var(--surface-2)" }}>
          <Field label="판정">
            <select className="select" value={det.judge.mode}
              onChange={(e) => edit((d) => { d.detection.judge.mode = e.target.value as AppConfig["detection"]["judge"]["mode"]; }, "판정 기준 변경")}>
              <option value="intersect">선에 닿으면 차량 있음</option>
              <option value="cover_ratio">선이 덮인 비율로 판단</option>
            </select>
          </Field>
          <Field label="덮임 비율 기준">
            <TextInput mono type="number" step="0.05" value={det.judge.cover_ratio}
              onCommit={(v) => edit((d) => { d.detection.judge.cover_ratio = num(v); }, "덮임 비율 변경")} />
          </Field>
          <Field label="겹친 칸 기준">
            <TextInput mono type="number" step="0.05" value={det.judge.cover_ratio_shared}
              onCommit={(v) => edit((d) => { d.detection.judge.cover_ratio_shared = num(v); }, "겹친 칸 기준 변경")} />
          </Field>
          <Field label="연속 일치 횟수">
            <TextInput mono type="number" step="1" value={det.stabilize.count}
              onCommit={(v) => edit((d) => { d.detection.stabilize.count = Math.max(1, num(v)); }, "연속 일치 횟수 변경")} />
          </Field>
        </div>
      )}
      {det.preset === "custom" && compact && <span className="meta">직접 설정 값은 시스템 설정에서 고칩니다</span>}
      <div className={`form-grid${compact ? " form-grid--2" : ""}`}>
        <Field label="차량 인식 기준 (0~1)">
          <TextInput mono type="number" step="0.05" value={car.conf}
            onCommit={(v) => edit((d) => { d.detection.classes.car = { ...(d.detection.classes.car ?? { enabled: true }), conf: num(v) }; }, "차량 인식 기준 변경")} />
        </Field>
        {!compact && (
          <Field label="모델 (models/ 아래 이름)">
            <TextInput mono value={det.model ?? ""} placeholder="없음 (fixture 검출기)"
              onCommit={(v) => edit((d) => { d.detection.model = v.trim() || null; }, "모델 변경")} />
          </Field>
        )}
      </div>
    </>
  );
}

export function LampFields() {
  const { cfg, edit } = useCfg();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {cfg.slot_types.map((t) => (
        <div key={t.id} className="lamp-row">
          <span className="lamp-row__name">{t.name}</span>
          <div role="radiogroup" aria-label={`${t.name} 빈칸 색`} style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {INDICATOR_COLORS.map((c) => (
              <button key={c.id} type="button" role="radio" aria-checked={t.color_available === c.id} aria-label={c.name} title={c.name}
                className="swatch" onClick={() => edit((d) => {
                  const x = d.slot_types.find((s) => s.id === t.id);
                  if (x) x.color_available = c.id;
                }, `${t.name} 만공등 → ${c.name}`)}>
                <span className="swatch__fill" style={{ background: c.hex }} />
              </button>
            ))}
          </div>
        </div>
      ))}
      <div className="lamp-row">
        <span className="lamp-row__name">만차</span>
        <span className="meta" style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          <span className="swatch__fill" style={{ background: FULL_LAMP.hex, display: "inline-block" }} />{FULL_LAMP.name} (고정)
        </span>
      </div>
    </div>
  );
}

const NEW_PROFILE: CameraProfile = {
  snapshot_url: "http://{ip}:{port}/snapshot.jpg", auth: "digest", user: "admin", password: "",
  ref_size: [1280, 960], views: [[0, 0, 640, 480], [640, 0, 640, 480]],
};

export function ProfilesFields() {
  const { cfg, edit, toast } = useCfg();
  const [newName, setNewName] = useState("");
  const rename = (from: string, to: string) => {
    const n = to.trim();
    if (!n || n === from) return;
    if (cfg.camera_profiles[n]) return toast("같은 이름의 프로필이 있습니다");
    edit((d) => {
      d.camera_profiles = Object.fromEntries(Object.entries(d.camera_profiles).map(([k, v]) => [k === from ? n : k, v]));
      for (const c of d.cameras) if (c.profile === from) c.profile = n;
      if (d.camera_profiles[n].password === "****") d.camera_profiles[n].password = "";
    }, `프로필 이름 → ${n}`);
    if (cfg.camera_profiles[from].password === "****") toast("이름을 바꿨으니 공통 비밀번호를 다시 입력하세요", 4000);
  };
  const setP = (name: string, fn: (p: CameraProfile) => void, note: string) =>
    edit((d) => { fn(d.camera_profiles[name]); }, note);

  return (
    <>
      {Object.entries(cfg.camera_profiles).map(([name, p]) => {
        const used = cfg.cameras.filter((c) => c.profile === name).length;
        const [rw, rh] = p.ref_size;
        return (
          <div key={name} style={{ border: "1px solid var(--line)", borderRadius: 10, overflow: "hidden" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", background: "var(--surface-2)", borderBottom: "1px solid var(--line)" }}>
              <span style={{ fontWeight: 600 }}>{name}</span>
              <span className="meta">카메라 {used}대 사용 중</span>
              <span className="spacer" />
              <button type="button" className="btn btn--danger" disabled={used > 0} title={used ? "사용 중인 프로필은 삭제할 수 없습니다" : undefined}
                onClick={() => edit((d) => { delete d.camera_profiles[name]; }, `프로필 ${name} 삭제`)}>삭제</button>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 20, padding: 16 }}>
              <div className="form-grid form-grid--2" style={{ flex: "999 1 360px", minWidth: 0 }}>
                <Field label="이름"><TextInput value={name} onCommit={(v) => rename(name, v)} /></Field>
                <Field label="인증">
                  <select className="select" value={p.auth} onChange={(e) => setP(name, (x) => { x.auth = e.target.value as CameraProfile["auth"]; }, "인증 방식 변경")}>
                    <option value="digest">다이제스트 (Digest)</option>
                    <option value="basic">기본 (Basic)</option>
                    <option value="none">인증 없음</option>
                  </select>
                </Field>
                <Field label="스냅샷 주소 · {ip}, {port}에 카메라 값이 들어감" className="span-2">
                  <TextInput mono value={p.snapshot_url} onCommit={(v) => setP(name, (x) => { x.snapshot_url = v.trim(); }, "스냅샷 주소 변경")} />
                </Field>
                <Field label="공통 사용자"><TextInput value={p.user} onCommit={(v) => setP(name, (x) => { x.user = v; }, "공통 사용자 변경")} /></Field>
                <Field label="공통 비밀번호"><TextInput type="password" value={p.password} onCommit={(v) => setP(name, (x) => { x.password = v; }, "공통 비밀번호 변경")} /></Field>
                <Field label="기준 해상도 (가로x세로)">
                  <TextInput mono value={`${rw}x${rh}`} onCommit={(v) => {
                    const m = /^(\d+)\s*[x×]\s*(\d+)$/.exec(v.trim());
                    if (!m) return toast("예: 1280x960");
                    setP(name, (x) => { x.ref_size = [Number(m[1]), Number(m[2])]; }, "기준 해상도 변경");
                  }} />
                </Field>
                <Field label="분석 영역 (x,y,가로,세로; …)">
                  <TextInput mono value={p.views.map((v) => v.join(",")).join("; ")} onCommit={(v) => {
                    const views = v.split(";").map((s) => s.trim()).filter(Boolean).map((s) => s.split(",").map(Number));
                    if (!views.length || views.some((x) => x.length !== 4 || x.some(Number.isNaN))) return toast("예: 0,0,640,480; 640,0,640,480");
                    setP(name, (x) => { x.views = views as CameraProfile["views"]; }, "분석 영역 변경");
                  }} />
                </Field>
              </div>
              <ViewsPreview profile={p} />
            </div>
          </div>
        );
      })}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <input className="input" style={{ maxWidth: 240 }} placeholder="새 프로필 이름" value={newName} onChange={(e) => setNewName(e.target.value)} />
        <button type="button" className="btn btn--soft" onClick={() => {
          const n = newName.trim();
          if (!n || cfg.camera_profiles[n]) return toast("이름을 확인하세요");
          edit((d) => { d.camera_profiles[n] = structuredClone(NEW_PROFILE); }, `프로필 ${n} 추가`);
          setNewName("");
        }}><Icon name="plus" size={14} />프로필 추가</button>
      </div>
    </>
  );
}

function ViewsPreview({ profile }: { profile: CameraProfile }) {
  const [rw, rh] = profile.ref_size;
  return (
    <div style={{ flex: "1 1 200px", display: "flex", flexDirection: "column", gap: 6 }}>
      <span className="meta">분석 영역 · {profile.views.length}개</span>
      <svg viewBox={`0 0 ${rw} ${rh}`} role="img" aria-label="기준 해상도 안의 분석 영역"
        style={{ width: "100%", aspectRatio: `${rw} / ${rh}`, borderRadius: 8, background: "var(--media)" }}>
        {profile.views.map((v, i) => (
          <g key={i}>
            <rect x={v[0]} y={v[1]} width={v[2]} height={v[3]} fill="var(--view-fill)" stroke="var(--view-line)" strokeWidth={rw / 200} />
            <text x={v[0] + v[2] / 2} y={v[1] + v[3] / 2} fill="var(--media-veil-text)" fontSize={rw / 20} textAnchor="middle" dominantBaseline="central">{i + 1}</text>
          </g>
        ))}
      </svg>
    </div>
  );
}

export function FileFields() {
  const { reload, toast } = useCfg();
  const fileRef = useRef<HTMLInputElement>(null);
  const onFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    try {
      const data = JSON.parse(await f.text());
      if (!window.confirm("가져온 설정으로 지금 설정을 모두 덮어쓰고 바로 저장합니다. 계속할까요?")) return;
      await api.saveConfig(data);
      await reload();
      toast("가져왔습니다");
    } catch (err) {
      toast(`가져오기 실패: ${(err as Error).message}`, 5000);
    }
  };
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
      <a className="btn" href={api.exportUrl(false)}>내보내기 (비밀번호 제외)</a>
      <a className="btn" href={api.exportUrl(true)}>내보내기 (비밀번호 포함)</a>
      <span className="spacer" />
      <button type="button" className="btn btn--danger" onClick={() => fileRef.current?.click()}>가져오기…</button>
      <input ref={fileRef} type="file" accept=".json,application/json" hidden onChange={onFile} />
    </div>
  );
}
