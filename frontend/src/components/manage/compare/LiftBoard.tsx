// B 뷰 — 리프트 검증 보드: KPI 요약 타일 + 게시물별 행 테이블 (행 클릭 = 상세 선택)
import type { BoardRow } from './types';
import { rate } from './types';
import { VerdictBadge } from './VerdictBadge';

function Tile({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] px-4 py-3">
      <p className="text-xs text-[#8B95A1]">{label}</p>
      <p className="text-2xl font-extrabold text-[#191F28] dark:text-[#F2F4F6] mt-1">{value}</p>
      <p className="text-[11px] text-[#B0B8C1] mt-0.5">{sub}</p>
    </div>
  );
}

export function LiftBoard({
  rows,
  selected,
  onSelect,
}: {
  rows: BoardRow[];
  selected: number;
  onSelect: (idx: number) => void;
}) {
  const n = rows.length || 1;
  const avgRatio = rows.reduce((s, r) => s + r.lift.reach_lift_ratio, 0) / n;
  const avgCtr = rows.reduce((s, r) => s + rate(r.lift.paid.clicks, r.lift.paid.impressions), 0) / n;
  const counts = rows.reduce(
    (a, r) => ({ ...a, [r.lift.verdict]: (a[r.lift.verdict] ?? 0) + 1 }),
    {} as Record<string, number>,
  );
  const passRate = Math.round(((counts.pass ?? 0) / n) * 100);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Tile label="검증한 게시물" value={`${rows.length}`} sub="개 (데모)" />
        <Tile label="평균 증분 도달" value={`×${avgRatio.toFixed(1)}`} sub="오가닉 대비" />
        <Tile label="평균 광고 CTR" value={`${avgCtr.toFixed(1)}%`} sub="링크 클릭 기준" />
        <Tile
          label="검증 통과율"
          value={`${passRate}%`}
          sub={`${counts.pass ?? 0} 통과 / ${counts.caution ?? 0} 주의 / ${counts.fail ?? 0} 미달`}
        />
      </div>

      <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-[#F9FAFB] dark:bg-[#1A202C] text-[#8B95A1] text-xs">
              <th className="text-left font-semibold px-4 py-2.5">게시물</th>
              <th className="text-right font-semibold px-3 py-2.5">오가닉 도달</th>
              <th className="text-right font-semibold px-3 py-2.5">광고 도달</th>
              <th className="text-right font-semibold px-3 py-2.5">증분(배수)</th>
              <th className="text-right font-semibold px-3 py-2.5 hidden md:table-cell">오가닉 참여율</th>
              <th className="text-right font-semibold px-3 py-2.5">광고 CTR</th>
              <th className="text-right font-semibold px-3 py-2.5 hidden md:table-cell">지출</th>
              <th className="text-right font-semibold px-4 py-2.5">검증</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const er = rate(r.lift.organic.engagement, r.lift.organic.impressions);
              const ctr = rate(r.lift.paid.clicks, r.lift.paid.impressions);
              const ratioColor =
                r.lift.verdict === 'pass'
                  ? 'text-green-600 dark:text-green-400'
                  : r.lift.verdict === 'caution'
                    ? 'text-amber-600 dark:text-amber-400'
                    : 'text-red-600 dark:text-red-400';
              return (
                <tr
                  key={r.lift.post_id}
                  onClick={() => onSelect(i)}
                  className={`cursor-pointer border-t border-[#F2F4F6] dark:border-[#2D3748] ${
                    selected === i ? 'bg-[#EAF3FF] dark:bg-[#1E293B]' : 'hover:bg-[#F9FAFB] dark:hover:bg-[#1A202C]'
                  }`}
                >
                  <td className="px-4 py-3 font-medium text-[#191F28] dark:text-[#F2F4F6]">{r.title}</td>
                  <td className="px-3 py-3 text-right tabular-nums text-[#4E5968] dark:text-[#C9CED6]">
                    {r.lift.organic.reach.toLocaleString()}
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums font-semibold text-[#191F28] dark:text-[#F2F4F6]">
                    {r.lift.paid.reach.toLocaleString()}
                  </td>
                  <td className={`px-3 py-3 text-right tabular-nums font-bold ${ratioColor}`}>
                    ×{r.lift.reach_lift_ratio}
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums text-[#4E5968] dark:text-[#C9CED6] hidden md:table-cell">
                    {er.toFixed(1)}%
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums text-[#4E5968] dark:text-[#C9CED6]">
                    {ctr.toFixed(1)}%
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums text-[#4E5968] dark:text-[#C9CED6] hidden md:table-cell">
                    ₩{r.lift.paid.spend_krw.toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <VerdictBadge verdict={r.lift.verdict} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
