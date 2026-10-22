import type { ReactNode } from "react";
import { BasicFields, FileFields, JudgeFields, LampFields, ProfilesFields, ServerFields } from "../settings/sections";
import { useCfg } from "../state/AppState";

const SECTIONS = [
  { id: "basic", title: "기본 정보", note: "보드명은 카메라의 '담당 보드'와 비교해 이 보드가 처리할 카메라를 정합니다. 전송용 보드 IP를 비우면 자동으로 읽습니다." },
  { id: "server", title: "서버 전송", note: "카메라마다 판정 주기마다 주차면 상태를 보냅니다. 전송 테스트는 저장된 설정으로 한 번 보내 봅니다." },
  { id: "judge", title: "판정 방식", note: "칸 선분과 차량 박스로 칸마다 차량 유무를 정합니다." },
  { id: "lamp", title: "만공등 색", note: "빈칸이 있을 때 켜질 색을 주차 종류별로 고릅니다. 모두 차면 항상 빨간색입니다." },
  { id: "profile", title: "카메라 프로필", note: "기종별 스냅샷 주소, 인증, 공통 계정, 분석할 화면 영역입니다. 계정이 다른 카메라만 카메라 설정에서 '개별 계정'을 켭니다." },
  { id: "file", title: "설정 파일", note: "현장 전체 설정(카메라, 칸, 서버)을 파일로 내보내거나 가져옵니다. 가져오면 지금 설정을 모두 덮어쓰고 바로 저장됩니다." },
] as const;

const BODY: Record<(typeof SECTIONS)[number]["id"], ReactNode> = {
  basic: <BasicFields />, server: <ServerFields />, judge: <JudgeFields />, lamp: <LampFields />, profile: <ProfilesFields />, file: <FileFields />,
};

export function SettingsPage() {
  const { system } = useCfg();
  return (
    <div className="page page--narrow">
      <nav className="toc" aria-label="설정 목차">
        <h1 className="title" style={{ margin: "0 0 10px 10px" }}>시스템 설정</h1>
        {SECTIONS.map((s) => <a key={s.id} className="toc__link" href={`#set-${s.id}`}>{s.title}</a>)}
        {system && (
          <div className="meta" style={{ padding: "16px 10px", display: "flex", flexDirection: "column", gap: 2 }}>
            <span className="mono">v{system.version}</span>
            <span>{system.board_model}</span>
            <span className="mono">{system.board_ip}</span>
          </div>
        )}
      </nav>
      <main className="page__main">
        {SECTIONS.map((s) => (
          <section key={s.id} id={`set-${s.id}`} className="panel section">
            <div>
              <h2 className="section-title">{s.title}</h2>
              <p className="note" style={{ marginTop: 4 }}>{s.note}</p>
            </div>
            {BODY[s.id]}
          </section>
        ))}
      </main>
    </div>
  );
}
