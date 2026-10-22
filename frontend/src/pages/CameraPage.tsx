import { useEffect, useMemo, useState } from "react";
import type { Camera, SlotTypeId } from "../api/types";
import { Icon } from "../components/Icon";
import { LineEditor } from "../components/LineEditor";
import { Check, CloseButton, Dialog, Field, TextInput, TypePicker } from "../components/ui";
import { useCameraView, useSlotEditing } from "../components/useCamera";
import { fmtPoint, handledHere, ipRange, slotType, stateLabel, stateTextClass } from "../lib/domain";
import { useCfg } from "../state/AppState";

export function CameraPage({ selectedIp, setSelectedIp }: { selectedIp: string | null; setSelectedIp: (ip: string | null) => void }) {
  const { cfg, status, alive, edit, toast } = useCfg();
  const [query, setQuery] = useState("");
  const [adding, setAdding] = useState(false);
  const [newType, setNewType] = useState<SlotTypeId>("normal");
  const cams = cfg.cameras;
  const ip = selectedIp && cams.some((c) => c.ip === selectedIp) ? selectedIp : cams[0]?.ip ?? null;
  const cam = cams.find((c) => c.ip === ip);
  const editing = useSlotEditing(ip ?? undefined, newType);
  const view = useCameraView(cam);
  const list = cams.filter((c) => c.ip.includes(query.trim()));

  const { setSelected } = editing;
  useEffect(() => setSelected(null), [ip, setSelected]);

  const setCam = (fn: (c: Camera) => void, note: string) =>
    edit((d) => { const c = d.cameras.find((x) => x.ip === ip); if (c) fn(c); }, note);

  return (
    <div className="page">
      <aside className="panel page__list" aria-label="카메라 목록">
        <div className="list-panel__head row row--between">
          <h2 className="section-title">카메라 <span className="mono muted regular">{cams.length}</span></h2>
          <button type="button" className="btn btn--soft" onClick={() => setAdding(true)}><Icon name="plus" size={14} />추가</button>
        </div>
        <div className="list-panel__search">
          <input className="input" type="search" aria-label="IP로 찾기" placeholder="IP로 찾기" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <ul className="cam-list">
          {list.map((c) => {
            const here = handledHere(cfg, c);
            const st = alive && here ? status.cameras[c.ip]?.status : undefined;
            const dot = !here ? "" : st === "no_response" ? "dot--bad" : st ? "dot--ok" : "";
            return (
              <li key={c.ip}>
                <button type="button" className="cam-item" aria-current={c.ip === ip} onClick={() => setSelectedIp(c.ip)} data-other={!here || undefined}>
                  <span className={`dot ${dot}`} />
                  <span className="cam-item__ip">{c.ip}</span>
                  <span className="meta">{!c.enabled ? "사용 안 함" : `${c.slots.length}칸`}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </aside>

      {!cam || !view ? (
        <main className="page__main">
          <div className="panel empty">
            <span>등록된 카메라가 없습니다.</span>
            <button type="button" className="btn btn--primary" onClick={() => setAdding(true)}><Icon name="plus" />카메라 추가하기</button>
          </div>
        </main>
      ) : (
        <>
          <section className="page__main" aria-label="칸 선분 편집">
            <div className="row row--wrap page-title">
              <h1 className="title mono strong">{cam.ip}</h1>
              {view.offline && <span className="badge badge--bad">응답 없음</span>}
              {!cam.enabled && <span className="badge badge--off">사용 안 함</span>}
              <span className="meta">{cfg.camera_profiles[cam.profile]?.ref_size.join("×")} 중 분석 영역 {cfg.camera_profiles[cam.profile]?.views.length ?? 0}개</span>
            </div>

            <LineEditor cam={cam} editing={editing} newType={newType} setNewType={setNewType} />

            <div className="panel table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">칸</th><th scope="col">주차 종류</th><th scope="col">시작 (x, y)</th><th scope="col">끝 (x, y)</th>
                    <th scope="col">현재 판정</th><th scope="col"><span className="sr-only">삭제</span></th>
                  </tr>
                </thead>
                <tbody>
                  {cam.slots.length === 0 && <tr><td colSpan={6} className="meta">아직 칸이 없습니다</td></tr>}
                  {cam.slots.map((s) => {
                    const st = view.states(s.no);
                    return (
                      <tr key={s.no} aria-selected={editing.selected === s.no}>
                        <td><button type="button" className="btn btn--ghost mono text-plain strong" aria-label={`${s.no}번 칸 선택`} onClick={() => editing.setSelected(s.no)}>{s.no}</button></td>
                        <td>
                          <span className="row">
                            <span className="type-bar" style={{ background: slotType(s.type).color }} />
                            <select className="select select--inline" aria-label={`${s.no}번 칸 주차 종류`} value={s.type}
                              onChange={(e) => editing.setType(s.no, e.target.value as SlotTypeId)}>
                              {cfg.slot_types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                            </select>
                          </span>
                        </td>
                        <td className="mono muted">{fmtPoint(s.line[0])}</td>
                        <td className="mono muted">{fmtPoint(s.line[1])}</td>
                        <td><span className={`chip chip--label${st === true ? " chip--occ" : st === false ? " chip--free" : ""}`}>{stateLabel(st)}</span></td>
                        <td className="cell-end">
                          <button type="button" className="btn btn--icon btn--ghost muted" aria-label={`${s.no}번 칸 삭제`} onClick={() => editing.remove(s.no)}>
                            <Icon name="trash" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          <aside className="page__side" aria-label="카메라 정보">
            <SelectedSlot cam={cam} editing={editing} states={view.states} />
            <div className="panel panel__body">
              <h2 className="section-title">카메라 정보</h2>
              <Field label="카메라 IP">
                <TextInput mono value={cam.ip} onCommit={(v) => {
                  const nv = v.trim();
                  if (!/^\d{1,3}(\.\d{1,3}){3}$/.test(nv)) return toast("IP 형식을 확인하세요");
                  if (cfg.cameras.some((c) => c.ip === nv)) return toast("이미 있는 IP입니다");
                  setCam((c) => { c.ip = nv; }, `IP 변경 → ${nv}`);
                  setSelectedIp(nv);
                }} />
              </Field>
              <div className="form-grid form-grid--2">
                <Field label="포트"><TextInput mono type="number" value={cam.port} onCommit={(v) => setCam((c) => { c.port = Number(v) || 80; }, "포트 변경")} /></Field>
                <Field label="프로필">
                  <select className="select" value={cam.profile} onChange={(e) => setCam((c) => { c.profile = e.target.value; }, "프로필 변경")}>
                    {Object.keys(cfg.camera_profiles).map((p) => <option key={p}>{p}</option>)}
                  </select>
                </Field>
                <Field label="담당 보드"><TextInput value={cam.board ?? ""} placeholder="모든 보드" onCommit={(v) => setCam((c) => { c.board = v.trim() || null; }, "담당 보드 변경")} /></Field>
                <Field label="컨트롤러 IP"><TextInput mono value={cam.controller_ip ?? ""} placeholder="없음" onCommit={(v) => setCam((c) => { c.controller_ip = v.trim() || null; }, "컨트롤러 IP 변경")} /></Field>
              </div>
              <div className="divided">
                <Check label="판정에 사용" checked={cam.enabled} onChange={(v) => setCam((c) => { c.enabled = v; }, v ? "판정 사용" : "판정 사용 안 함")} />
                <Check label="개별 계정" sub="끄면 프로필의 공통 계정 사용" checked={cam.own_account} onChange={(v) => setCam((c) => { c.own_account = v; }, "계정 방식 변경")} />
              </div>
              {cam.own_account && (
                <div className="form-grid form-grid--2">
                  <Field label="사용자"><TextInput value={cam.user} onCommit={(v) => setCam((c) => { c.user = v; }, "사용자 변경")} /></Field>
                  <Field label="비밀번호"><TextInput type="password" value={cam.password} onCommit={(v) => setCam((c) => { c.password = v; }, "비밀번호 변경")} /></Field>
                </div>
              )}
              <button type="button" className="btn btn--danger" onClick={() => {
                if (!window.confirm(`${cam.ip} 카메라를 삭제할까요? (저장해야 반영됩니다)`)) return;
                edit((d) => { d.cameras = d.cameras.filter((c) => c.ip !== cam.ip); }, `${cam.ip} 삭제`);
                setSelectedIp(null);
              }}>이 카메라 삭제</button>
            </div>
          </aside>
        </>
      )}

      {adding && <AddCameraDialog onClose={() => setAdding(false)} onAdded={(first) => setSelectedIp(first)} />}
    </div>
  );
}

function SelectedSlot({ cam, editing, states }: {
  cam: Camera; editing: ReturnType<typeof useSlotEditing>; states: (no: number) => boolean | null;
}) {
  const s = cam.slots.find((x) => x.no === editing.selected);
  if (!s) return <div className="panel panel__body"><span className="meta">선이나 번호를 누르면 그 칸을 고칠 수 있습니다</span></div>;
  const st = states(s.no);
  return (
    <div className="panel panel__body panel--active">
      <div className="row row--between">
        <h2 className="section-title">선택한 칸</h2>
        <span className="mono section-title">{s.no}번</span>
      </div>
      <Field label="주차 종류">
        <TypePicker columns={2} value={s.type} onPick={(t) => editing.setType(s.no, t)} label="선택한 칸 주차 종류" />
      </Field>
      <div className="row row--between soft-box fs-control">
        <span className="muted">현재 판정</span>
        <span className={`strong ${stateTextClass(st)}`}>{stateLabel(st)}</span>
      </div>
      <button type="button" className="btn btn--danger" onClick={() => editing.remove(s.no)}><Icon name="trash" size={14} />이 칸 삭제</button>
    </div>
  );
}

function AddCameraDialog({ onClose, onAdded }: { onClose: () => void; onAdded: (firstIp: string) => void }) {
  const { cfg, edit } = useCfg();
  const profiles = Object.keys(cfg.camera_profiles);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [port, setPort] = useState("80");
  const [profile, setProfile] = useState(profiles[0] ?? "");
  const [board, setBoard] = useState(cfg.site.board_name ?? "");
  const r = useMemo(() => (start.trim() ? ipRange(start, end) : null), [start, end]);
  const have = new Set(cfg.cameras.map((c) => c.ip));
  const ips = r && "ips" in r ? r.ips : [];
  const fresh = ips.filter((x) => !have.has(x));

  const add = () => {
    if (!fresh.length) return;
    edit((d) => {
      for (const ip of fresh) {
        d.cameras.push({ ip, port: Number(port) || 80, profile, own_account: false, user: "", password: "",
          controller_ip: null, board: board.trim() || null, ref_size: null, enabled: true, slots: [] });
      }
    }, `카메라 ${fresh.length}대 추가`);
    onAdded(fresh[0]);
    onClose();
  };

  return (
    <Dialog label="카메라 추가" onClose={onClose}>
      <div className="panel__head">
        <h2 className="section-title spacer">카메라 추가</h2>
        <CloseButton onClick={onClose} />
      </div>
      {profiles.length === 0 ? (
        <div className="panel__body"><p className="note">먼저 시스템 설정에서 카메라 프로필을 만드세요.</p></div>
      ) : (
        <div className="panel__body">
          <p className="note">한 대만 추가하려면 시작 IP만 입력하세요. 여러 대는 끝 번호(예: 30)나 끝 IP를 입력합니다. 계정은 프로필의 공통 계정을 사용합니다.</p>
          <div className="form-grid form-grid--2">
            <Field label="시작 IP"><input className="input mono" autoFocus value={start} placeholder="192.168.13.26" onChange={(e) => setStart(e.target.value)} /></Field>
            <Field label="끝 (번호 또는 IP)"><input className="input mono" value={end} placeholder="비우면 한 대" onChange={(e) => setEnd(e.target.value)} /></Field>
            <Field label="포트"><input className="input mono" type="number" value={port} onChange={(e) => setPort(e.target.value)} /></Field>
            <Field label="프로필">
              <select className="select" value={profile} onChange={(e) => setProfile(e.target.value)}>
                {profiles.map((p) => <option key={p}>{p}</option>)}
              </select>
            </Field>
            <Field label="담당 보드" className="span-2"><input className="input" value={board} placeholder="모든 보드" onChange={(e) => setBoard(e.target.value)} /></Field>
          </div>
          <div className="stack soft-box">
            <div className="row row--between row--baseline gap-2-5">
              <span className="strong fs-control">추가될 카메라 <span className="mono text-accent">{fresh.length}대</span></span>
              {ips.length > fresh.length && <span className="meta">이미 있는 {ips.length - fresh.length}대는 건너뜀</span>}
            </div>
            {r && "error" in r && <span className="text-bad fs-control">{r.error}</span>}
            <div className="chips">
              {ips.map((x) => (
                <span key={x} className={`ip-tag mono${have.has(x) ? " ip-tag--exists" : ""}`}>{x}</span>
              ))}
            </div>
          </div>
        </div>
      )}
      <div className="dialog__foot">
        <button type="button" className="btn" onClick={onClose}>취소</button>
        <button type="button" className="btn btn--primary" disabled={!fresh.length} onClick={add}>{fresh.length}대 추가</button>
      </div>
    </Dialog>
  );
}
