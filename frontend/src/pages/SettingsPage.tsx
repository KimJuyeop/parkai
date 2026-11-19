import { useEffect, useState, type ReactNode } from "react";
import { BasicFields, FileFields, JudgeFields, LampFields, MaintFields, ProfilesFields, RecordFields, ServerFields } from "../settings/sections";
import { useCfg } from "../state/AppState";

const SECTIONS = [
  { id: "basic", title: "기본 정보", note: "보드명은 카메라의 '담당 보드'와 비교해 이 보드가 처리할 카메라를 정합니다. 비워 두면 모든 카메라를 처리합니다. 보드가 한 대인 현장은 비워 둡니다." },
  { id: "server", title: "서버 전송", note: "카메라마다 판정 주기마다 주차면 상태를 보냅니다. 전송 테스트는 저장된 설정으로 한 번 보내 봅니다." },
  { id: "judge", title: "판정", note: "칸 선분과 차량 박스로 칸마다 차량 유무를 정합니다. 차량 인식 기준을 낮추면 어둡거나 그늘진 차도 잡지만, 너무 낮추면 차가 아닌 곳에도 박스가 생깁니다. 확인 횟수를 늘리면 잠깐 가려지거나 잘못 잡힌 판정에 덜 흔들리지만 반영이 늦어집니다. 차가 있는 칸을 빈칸으로 안내하는 쪽이 더 위험하므로, 늘린다면 빈칸 확인 쪽을 먼저 늘립니다." },
  { id: "lamp", title: "만공등", note: "카메라마다 하나입니다. 빈칸이 있을 때 켜질 색을 주차 종류별로 고르고, 모두 차면 항상 빨간색입니다. 색이 바뀔 때와 정해진 주기마다 카메라로 보냅니다." },
  { id: "record", title: "기록 이미지", note: "선과 검출 박스를 그린 사진을 상태가 바뀔 때와 정해진 간격마다 저장합니다. 현장 문의 때 원인을 확인하는 용도이고, 상한을 넘으면 오래된 것부터 지웁니다. 모니터링 화면과는 별개입니다. SD카드에 쓰므로 간격을 짧게 하면 카드 수명이 줄어듭니다." },
  { id: "profile", title: "카메라 프로필", note: "기종별 스냅샷 주소, 인증, 공통 계정, 렌즈 수, 분석할 화면 영역입니다. 렌즈가 2개인 카메라는 렌즈마다 사진을 따로 받습니다. 계정이 다른 카메라만 카메라 설정에서 '개별 계정'을 켭니다." },
  { id: "maint", title: "점검", note: "현장 운영에는 필요 없습니다. 보드가 쓰는 검출 모델을 확인하거나 바꿀 때만 씁니다. 모델을 바꾸면 판정 결과가 달라질 수 있습니다." },
  { id: "file", title: "설정 파일", note: "현장 전체 설정(카메라, 칸, 서버)을 파일로 내보내거나 가져옵니다. 가져오면 지금 설정을 모두 덮어쓰고 바로 저장됩니다." },
] as const;

const BODY: Record<(typeof SECTIONS)[number]["id"], ReactNode> = {
  basic: <BasicFields />, server: <ServerFields />, judge: <JudgeFields />, lamp: <LampFields />, record: <RecordFields />, profile: <ProfilesFields />, maint: <MaintFields />, file: <FileFields />,
};

/** 지금 화면에 보이는 절 (목차에서 강조) */
function useCurrentSection(ids: readonly string[]): string {
  const [current, setCurrent] = useState<string>(ids[0]);
  useEffect(() => {
    const visible = new Map<string, number>();
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) visible.set(e.target.id, e.isIntersecting ? e.intersectionRatio : 0);
        const shown = ids.filter((id) => (visible.get(`set-${id}`) ?? 0) > 0);
        // 맨 아래까지 내리면 마지막 절들이 함께 보이므로 마지막 것을 고른다
        const atBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4;
        const best = atBottom ? shown[shown.length - 1] : shown[0];
        if (best) setCurrent(best);
      },
      { threshold: [0, 0.25, 0.5, 1] },
    );
    for (const id of ids) {
      const el = document.getElementById(`set-${id}`);
      if (el) obs.observe(el);
    }
    return () => obs.disconnect();
  }, [ids]);
  return current;
}

const SECTION_IDS = SECTIONS.map((s) => s.id);

export function SettingsPage() {
  const { system } = useCfg();
  const current = useCurrentSection(SECTION_IDS);
  return (
    <div className="page page--narrow">
      <nav className="toc" aria-label="설정 목차">
        <h1 className="title toc__title">시스템 설정</h1>
        {SECTIONS.map((s) => (
          <a key={s.id} className="toc__link" href={`#set-${s.id}`} aria-current={current === s.id ? "true" : undefined}>{s.title}</a>
        ))}
        {system && (
          <div className="meta stack gap-half toc__info">
            <span className="mono">{system.version}</span>
          </div>
        )}
      </nav>
      <main className="page__main">
        {SECTIONS.map((s) => (
          <section key={s.id} id={`set-${s.id}`} className="panel section">
            <div>
              <h2 className="section-title">{s.title}</h2>
              <p className="note section__note">{s.note}</p>
            </div>
            {BODY[s.id]}
          </section>
        ))}
      </main>
    </div>
  );
}
