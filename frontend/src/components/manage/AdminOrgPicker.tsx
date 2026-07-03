// admin이 매니지먼트 데이터를 특정 조직으로 임퍼소네이션(X-Org-Id)해서 보는 드롭다운.
"use client";

import { useEffect, useState } from "react";
import { api, getAdminOrgId, setAdminOrgId } from "@/lib/api";
import { Select } from "@/components/ui/Select";

type Org = { id: string; name: string };

export function AdminOrgPicker() {
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [sel, setSel] = useState<string>(getAdminOrgId() ?? "");

  useEffect(() => {
    let alive = true;
    api.admin
      .organizations()
      .then((list) => {
        if (alive && Array.isArray(list)) {
          setOrgs(list.map((o) => ({ id: o.id, name: o.name })));
        }
      })
      .catch(() => {
        if (alive) setOrgs([]); // 실패 시 빈 목록 — 전체(all orgs)만 선택 가능.
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <label className="flex items-center gap-2 text-sm text-[#4E5968] dark:text-[#9CA3AF]">
      <span className="font-medium">조직</span>
      <Select
        aria-label="조직 선택"
        className="min-w-[180px]"
        value={sel}
        onChange={(v) => {
          setSel(v);
          setAdminOrgId(v || null);
          // 선택 변경 시 전체 매니지먼트 데이터를 새 스코프로 다시 불러온다.
          window.location.reload();
        }}
        options={[
          { value: "", label: "전체 (all orgs)" },
          ...orgs.map((o) => ({ value: o.id, label: o.name })),
        ]}
      />
    </label>
  );
}
