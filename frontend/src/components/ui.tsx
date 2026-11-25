import { useEffect, useId, type CSSProperties, type ReactNode } from "react";
import { MASK, SLOT_TYPES, type SlotState } from "../lib/domain";
import type { SlotTypeId } from "../api/types";
import { Icon } from "./Icon";

export function Field({ label, children, className = "" }: { label: string; children: ReactNode; className?: string }) {
  return (
    <label className={`field ${className}`}>
      <span className="field__label">{label}</span>
      {children}
    </label>
  );
}

/** 입력을 마칠 때(포커스가 빠질 때) 값을 반영하는 글자 입력 */
export function TextInput({ value, onCommit, mono, type = "text", placeholder, step }: {
  value: string | number; onCommit: (v: string) => void; mono?: boolean; type?: string; placeholder?: string; step?: string;
}) {
  return (
    <input className={`input${mono ? " mono" : ""}`} type={type} step={step} placeholder={placeholder}
      defaultValue={value} key={String(value)}
      onBlur={(e) => e.target.value !== String(value) && onCommit(e.target.value)}
      onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />
  );
}

/**
 * 비밀번호 입력. 저장된 비밀번호는 화면에 오지 않으므로(MASK) 점 네 개 대신 빈칸에 '저장됨' 으로 보이고,
 * 입력했을 때만 바뀐다. 빈칸으로 두면 그대로, 지우려면 '지우기'.
 */
export function PasswordInput({ value, onCommit }: { value: string; onCommit: (v: string) => void }) {
  const saved = value === MASK;
  return (
    <span className="row gap-1-5">
      <input className="input" type="password" autoComplete="new-password" key={value}
        defaultValue={saved ? "" : value}
        placeholder={saved ? "저장됨 · 바꿀 때만 입력" : "없음"}
        onBlur={(e) => {
          const v = e.target.value;
          if (v ? v !== value : value && !saved) onCommit(v);
        }}
        onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />
      {value && <button type="button" className="btn btn--ghost" onClick={() => onCommit("")}>지우기</button>}
    </span>
  );
}

export function Check({ label, sub, checked, onChange }: { label: string; sub?: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="check">
      <span className="stack gap-0">
        <span>{label}</span>
        {sub && <span className="meta">{sub}</span>}
      </span>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
    </label>
  );
}

export function SlotChip({ no, state, type, title }: { no: number; state: SlotState; type: SlotTypeId; title?: string }) {
  const cls = state === true ? " chip--occ" : state === false ? " chip--free" : "";
  const short = SLOT_TYPES.find((t) => t.id === type)?.short;
  return (
    <span className={`chip${cls}`} title={title}>
      {no}
      {short && <span className="chip__mark">{short}</span>}
    </span>
  );
}

export function TypePicker({ value, onPick, label, columns = 4 }: {
  value: SlotTypeId; onPick: (t: SlotTypeId) => void; label: string; columns?: 2 | 4;
}) {
  return (
    <div className={`type-pick${columns === 2 ? " type-pick--2" : ""}`} role="radiogroup" aria-label={label}>
      {SLOT_TYPES.map((t) => (
        <button key={t.id} type="button" role="radio" aria-checked={t.id === value} className="type-pick__btn"
          onClick={() => t.id !== value && onPick(t.id)}>
          <span className="type-bar" style={{ background: t.color }} />
          {t.name}
        </button>
      ))}
    </div>
  );
}

export function Dialog({ label, width, onClose, children }: { label: string; width?: number; onClose: () => void; children: ReactNode }) {
  const id = useId();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby={id}
        style={width ? ({ "--dialog-w": `${width}px` } as CSSProperties) : undefined}>
        <span id={id} className="sr-only">{label}</span>
        {children}
      </div>
    </div>
  );
}

export function CloseButton({ onClick, label = "닫기" }: { onClick: () => void; label?: string }) {
  return (
    <button type="button" className="btn btn--icon" aria-label={label} onClick={onClick}>
      <Icon name="close" />
    </button>
  );
}
