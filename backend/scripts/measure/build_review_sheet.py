# [측정-정성평가] 측정 out 디렉터리를 사람이 눈으로 검수하는 자체완결 HTML 시트로 생성
r"""manifest.json + 이미지가 있는 측정 디렉터리를 받아 review.html 한 파일로 만든다.

- 이미지를 base64로 인라인 → 서버·인터넷 없이 브라우저로 바로 열어 검수.
- 이미지마다 카피(headline/body/cta) 요소별 판정 + 이미지 내 "모든 기타 텍스트"를 기록.
- measure_text_accuracy.py와 동일한 CSV 스키마로 내보내 VLM 판정과 나란히 비교.

실행 (backend 디렉터리에서)
  uv run python scripts\measure\build_review_sheet.py --dir scripts\measure\out\pipeline
  → scripts\measure\out\pipeline\review.html 생성 (브라우저로 열기)
  → 검수 후 "CSV 저장" → review_by_human.csv (VLM의 text_accuracy.csv와 동일 스키마)
"""

from __future__ import annotations

import argparse
import base64
import csv
import html
import json
import mimetypes
from pathlib import Path

# CSV 스키마·상태값은 measure_text_accuracy.py와 정확히 일치시킨다(양쪽 결과 비교용).
_STATUSES = [
    ("exact", "정확"),
    ("typo", "오탈자"),
    ("broken", "깨짐"),
    ("cut", "잘림"),
    ("missing", "누락"),
]

_HTML = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: "Pretendard", system-ui, sans-serif; background: #0f1115; color: #e7e9ee; }
  header { position: static; background: #171a21; border-bottom: 1px solid #2a2f3a;
           padding: 12px 20px; display: flex; gap: 20px; align-items: flex-start; flex-wrap: wrap; }
  header h1 { font-size: 15px; margin: 0 0 4px; font-weight: 700; }
  .dir { font-size: 12px; color: #8b93a3; }
  .summary { font-size: 12.5px; line-height: 1.7; color: #c7ccd6; flex: 1; min-width: 280px; }
  .summary b { color: #fff; }
  .controls { display: flex; gap: 8px; align-items: center; }
  button { font: inherit; font-size: 13px; padding: 8px 14px; border-radius: 8px; border: 1px solid #3a4150;
           background: #232936; color: #e7e9ee; cursor: pointer; }
  button.primary { background: #2f6bff; border-color: #2f6bff; color: #fff; font-weight: 600; }
  button:hover { filter: brightness(1.12); }
  main { padding: 20px; display: flex; flex-direction: column; gap: 18px; max-width: 1100px; margin: 0 auto; }
  .banner { background: #1e2b1e; border: 1px solid #2ecc71; color: #cfe9cf; border-radius: 10px;
            padding: 10px 14px; font-size: 12.5px; line-height: 1.6; }
  .card { display: grid; grid-template-columns: 360px 1fr; gap: 20px; background: #161a22;
          border: 1px solid #262c38; border-left: 4px solid #3a4150; border-radius: 12px; padding: 16px; }
  .card.clean { border-left-color: #2ecc71; }
  .card.defect { border-left-color: #ff5757; }
  .card img { width: 100%; border-radius: 8px; background: #000; }
  .imgwrap { display: flex; flex-direction: column; gap: 8px; }
  .meta { font-size: 11.5px; color: #8b93a3; word-break: break-all; }
  .el { padding: 10px 0; border-bottom: 1px dashed #262c38; }
  .el:last-of-type { border-bottom: none; }
  .exp { font-size: 13px; margin-bottom: 6px; }
  .exp .tag { display: inline-block; min-width: 62px; color: #8b93a3; font-size: 11.5px; }
  .exp .txt { color: #fff; }
  .radios { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 6px; }
  .radios label { font-size: 12px; padding: 4px 9px; border-radius: 6px; border: 1px solid #3a4150;
                  cursor: pointer; user-select: none; }
  .radios input { display: none; }
  .radios input:checked + span { }
  .radios label.on-exact { background: #14532d; border-color: #2ecc71; }
  .radios label.on-bad { background: #5c1a1a; border-color: #ff5757; }
  .seen { width: 100%; font: inherit; font-size: 12.5px; padding: 6px 8px; border-radius: 6px;
          border: 1px solid #2a3140; background: #0f1319; color: #e7e9ee; }
  .others { padding-top: 10px; }
  .others h4 { margin: 0 0 6px; font-size: 12.5px; color: #c7ccd6; }
  .others .hint { font-size: 11px; color: #8b93a3; margin-bottom: 8px; }
  .orow { display: flex; gap: 8px; margin-bottom: 6px; align-items: center; }
  .orow input { flex: 1; }
  .orow select { font: inherit; font-size: 12.5px; padding: 6px; border-radius: 6px;
                 border: 1px solid #2a3140; background: #0f1319; color: #e7e9ee; }
  .orow .del { padding: 5px 9px; }
  .addbtn { font-size: 12px; padding: 5px 10px; }
</style>
</head>
<body>
<header>
  <div>
    <h1>광고 이미지 텍스트 정성 검수</h1>
    <div class="dir">__HEADER__</div>
  </div>
  <div class="summary" id="summary">불러오는 중...</div>
  <div class="controls">
    <button class="primary" id="saveCsv">CSV 저장</button>
    <button id="resetAll">전체 초기화</button>
  </div>
</header>
<main id="main"></main>
<script>
const DATA = __DATA__;
const META = __META__;
const STATUSES = [["exact","정확"],["typo","오탈자"],["broken","깨짐"],["cut","잘림"],["missing","누락"]];
const OTHER_STATUSES = [["","판정"],["exact","정확"],["typo","오탈자"],["broken","깨짐"],["cut","잘림"]];
const COPY_ELS = ["headline","body","cta"];
const EL_KO = {headline:"헤드라인", body:"본문", cta:"CTA"};
const BAD = new Set(["typo","broken","cut","missing"]);
const KEY = "clickme_review::" + META.dir;

// 감사 모드 — VLM CSV로 프리필된 인스턴스·판정. localStorage에 사람 편집이 없으면 이걸로 초기화.
const PREFILL = {};
DATA.forEach(d => { if (d.prefill) PREFILL[d.file] = d.prefill; });

let state = {};
try { state = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { state = {}; }

function blank() {
  return { headline:{status:"",seen:""}, body:{status:"",seen:""}, cta:{status:"",seen:""}, others: [] };
}
function st(file) {
  if (!state[file]) {
    const p = PREFILL[file];
    state[file] = p ? JSON.parse(JSON.stringify(p)) : blank();
  }
  return state[file];
}
function save() { localStorage.setItem(KEY, JSON.stringify(state)); }

function el(tag, cls, txt) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (txt != null) n.textContent = txt;
  return n;
}

function render() {
  const main = document.getElementById("main");
  main.innerHTML = "";
  if (META.audit) {
    main.appendChild(el("div", "banner",
      "감사 모드 — VLM 판정을 미리 채웠습니다. 틀린 항목만 고치세요. " +
      "기타 텍스트는 시각적으로 구분되는 블록 1개 = 1행(라벨·배경·헛것 각각), 한 블록 내 여러 단어·줄은 쪼개지 않고, 정상 렌더도 '정확'으로 남깁니다."));
  }
  DATA.forEach(item => {
    const s = st(item.file);
    const card = el("div", "card");
    card.dataset.file = item.file;

    const iw = el("div", "imgwrap");
    const img = el("img"); img.src = item.img; img.alt = item.file; img.loading = "lazy";
    iw.appendChild(img);
    iw.appendChild(el("div", "meta",
      `${item.file}  ·  ${item.method || "?"}` +
      (item.template_id ? `  ·  ${item.template_id}` : "") +
      (item.strategy_type ? `  ·  ${item.strategy_type}` : "") +
      (item.name ? `  ·  ${item.name}` : "") +
      (item.prefill ? "  ·  VLM 프리필" : "")));
    card.appendChild(iw);

    const fields = el("div", "fields");
    COPY_ELS.forEach(elk => {
      const wrap = el("div", "el"); wrap.dataset.el = elk;
      const exp = el("div", "exp");
      exp.appendChild(el("span", "tag", EL_KO[elk]));
      exp.appendChild(el("span", "txt", " " + (item[elk] || "(없음)")));
      wrap.appendChild(exp);

      const radios = el("div", "radios");
      STATUSES.forEach(([val, ko]) => {
        const lab = el("label");
        const inp = el("input"); inp.type = "radio"; inp.name = item.file + "::" + elk; inp.value = val;
        if (s[elk].status === val) inp.checked = true;
        inp.addEventListener("change", () => { s[elk].status = val; save(); refresh(card, item); });
        lab.appendChild(inp); lab.appendChild(el("span", null, ko));
        radios.appendChild(lab);
      });
      wrap.appendChild(radios);

      const seen = el("input", "seen"); seen.placeholder = "실제로 보이는 텍스트(선택)";
      seen.value = s[elk].seen || "";
      seen.addEventListener("input", () => { s[elk].seen = seen.value; save(); });
      wrap.appendChild(seen);
      fields.appendChild(wrap);
    });

    // 이미지 내 기타 텍스트(상품 라벨·배경 문구·헛것 글자 등) — 모든 글자가 오타율에 반영되도록 기록
    const others = el("div", "others");
    others.appendChild(el("h4", null, "이미지 내 기타 텍스트"));
    others.appendChild(el("div", "hint",
      "시각적으로 구분되는 텍스트 블록 1개 = 1행(상품 라벨·배경·헛것 각각). 한 블록 내 여러 단어·줄은 쪼개지 않습니다. 정상 렌더도 '정확'으로 남깁니다."));
    const rows = el("div", "orows");
    others.appendChild(rows);
    const add = el("button", "addbtn", "+ 기타 텍스트 추가");
    add.addEventListener("click", () => { s.others.push({ seen:"", status:"" }); save(); render(); });
    others.appendChild(add);
    fields.appendChild(others);

    s.others.forEach((o, i) => {
      const orow = el("div", "orow");
      const seen = el("input", "seen"); seen.placeholder = "보이는 텍스트"; seen.value = o.seen || "";
      seen.addEventListener("input", () => { o.seen = seen.value; save(); });
      const sel = el("select");
      OTHER_STATUSES.forEach(([val, ko]) => {
        const opt = el("option", null, ko); opt.value = val;
        if (o.status === val) opt.selected = true;
        sel.appendChild(opt);
      });
      sel.addEventListener("change", () => { o.status = sel.value; save(); refresh(card, item); });
      const del = el("button", "del", "✕");
      del.addEventListener("click", () => { s.others.splice(i, 1); save(); render(); });
      orow.appendChild(seen); orow.appendChild(sel); orow.appendChild(del);
      rows.appendChild(orow);
    });

    card.appendChild(fields);
    main.appendChild(card);
    refresh(card, item);
  });
  updateSummary();
}

// 카드별 인스턴스(카피3 + 기타) 상태 → {judged, defects, complete}
function instances(file) {
  const s = st(file);
  const out = [];
  COPY_ELS.forEach(elk => { if (s[elk].status) out.push(s[elk].status); });
  s.others.forEach(o => { if (o.status) out.push(o.status); });
  return out;
}
function isComplete(file) { const s = st(file); return COPY_ELS.every(e => s[e].status); }

function refresh(card, item) {
  const inst = instances(item.file);
  const hasDefect = inst.some(x => BAD.has(x));
  card.classList.toggle("clean", isComplete(item.file) && !hasDefect);
  card.classList.toggle("defect", hasDefect);
  // 라디오 색
  COPY_ELS.forEach(elk => {
    const wrap = card.querySelector(`.el[data-el="${elk}"]`);
    if (!wrap) return;
    const s = st(item.file)[elk].status;
    wrap.querySelectorAll(".radios label").forEach(lab => {
      lab.classList.remove("on-exact", "on-bad");
      const v = lab.querySelector("input").value;
      if (v === s) lab.classList.add(v === "exact" ? "on-exact" : "on-bad");
    });
  });
  updateSummary();
}

function updateSummary() {
  const total = DATA.length;
  let complete = 0, cleanImgs = 0, judgedInst = 0, defectInst = 0;
  const perEl = {}; ["headline","body","cta","other"].forEach(e => perEl[e] = { j:0, exact:0 });
  DATA.forEach(item => {
    const s = st(item.file);
    const inst = instances(item.file);
    if (isComplete(item.file)) { complete++; if (!inst.some(x => BAD.has(x))) cleanImgs++; }
    judgedInst += inst.length;
    defectInst += inst.filter(x => BAD.has(x)).length;
    COPY_ELS.forEach(e => { if (s[e].status) { perEl[e].j++; if (s[e].status === "exact") perEl[e].exact++; } });
    s.others.forEach(o => { if (o.status) { perEl.other.j++; if (o.status === "exact") perEl.other.exact++; } });
  });
  const pct = (a, b) => b ? (a / b * 100).toFixed(0) : "–";
  const line = (e, ko) => perEl[e].j
    ? `${ko} 정확 ${perEl[e].exact}/${perEl[e].j} (${pct(perEl[e].exact, perEl[e].j)}%)` : `${ko} –`;
  document.getElementById("summary").innerHTML =
    `검수 진행 <b>${complete}/${total}</b> 이미지 &nbsp;·&nbsp; ` +
    `무결점 이미지 <b>${pct(cleanImgs, complete)}%</b> (완료분) &nbsp;·&nbsp; ` +
    `<b>전체 결함율 ${pct(defectInst, judgedInst)}%</b> (${defectInst}/${judgedInst} 텍스트, 이미지 내 모든 글자 기준)<br>` +
    [line("headline","헤드라인"), line("body","본문"), line("cta","CTA"), line("other","기타")].join(" &nbsp; ");
}

function csvCell(v) { return '"' + String(v == null ? "" : v).replace(/"/g, '""') + '"'; }
function exportCsv() {
  const header = ["file","method","element","status","expected","seen"];
  const lines = [header.join(",")];
  DATA.forEach(item => {
    const s = st(item.file);
    COPY_ELS.forEach(elk => {
      if (!s[elk].status) return;
      lines.push([item.file, item.method || "", elk, s[elk].status, item[elk] || "", s[elk].seen || ""].map(csvCell).join(","));
    });
    s.others.forEach(o => {
      if (!o.status) return;
      lines.push([item.file, item.method || "", "other", o.status, "", o.seen || ""].map(csvCell).join(","));
    });
  });
  const blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "review_by_human.csv";
  a.click();
  URL.revokeObjectURL(a.href);
}

document.getElementById("saveCsv").addEventListener("click", exportCsv);
document.getElementById("resetAll").addEventListener("click", () => {
  if (confirm("이 디렉터리의 검수 기록을 모두 지울까요?")) { state = {}; save(); render(); }
});
render();
</script>
</body>
</html>
"""


def _data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _read_vlm_prefill(path: Path) -> dict[str, dict]:
    """VLM 판정 CSV(text_accuracy.csv)를 파일별 프리필 구조로 변환 — 감사 모드.

    카피(headline/body/cta)는 슬롯에, other 행은 기타 인스턴스로. VLM이 나눈 경계·판정을
    그대로 시트에 채워 사람이 같은 인스턴스 위에서 확인·수정하게 한다.
    """
    prefill: dict[str, dict] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            file = row.get("file")
            if not file:
                continue
            rec = prefill.setdefault(
                file,
                {
                    "headline": {"status": "", "seen": ""},
                    "body": {"status": "", "seen": ""},
                    "cta": {"status": "", "seen": ""},
                    "others": [],
                },
            )
            element = row.get("element")
            entry = {"status": row.get("status") or "", "seen": row.get("seen") or ""}
            if element in ("headline", "body", "cta"):
                rec[element] = entry
            elif element == "other":
                rec["others"].append(entry)
            # 'any'(독립 판정 모드) 등은 카피 슬롯에 못 매핑하므로 무시
    return prefill


def main() -> None:
    parser = argparse.ArgumentParser(description="사람 정성 검수용 HTML 시트 생성")
    parser.add_argument("--dir", required=True, help="이미지+manifest.json 디렉터리")
    parser.add_argument("--limit", type=int, default=0, help="앞에서 N장만 포함 (0=전체)")
    parser.add_argument("--out", default=None, help="출력 HTML 경로 (기본 <dir>/review.html)")
    parser.add_argument(
        "--vlm-csv",
        default=None,
        help="VLM 판정 CSV로 프리필(감사 모드). 미지정 시 <dir>/text_accuracy.csv 자동 감지",
    )
    parser.add_argument(
        "--no-prefill", action="store_true", help="VLM CSV가 있어도 프리필하지 않음(백지 검수)"
    )
    args = parser.parse_args()

    img_dir = Path(args.dir)
    manifest = json.loads((img_dir / "manifest.json").read_text(encoding="utf-8"))
    entries = [e for e in manifest["items"] if e.get("status") == "ok" or "status" not in e]
    if args.limit:
        entries = entries[: args.limit]

    # 감사 모드 프리필 — VLM CSV 자동 감지(또는 --vlm-csv). --no-prefill이면 생략.
    prefill_by_file: dict[str, dict] = {}
    vlm_path = Path(args.vlm_csv) if args.vlm_csv else (img_dir / "text_accuracy.csv")
    if not args.no_prefill and vlm_path.exists():
        prefill_by_file = _read_vlm_prefill(vlm_path)

    items: list[dict] = []
    missing = 0
    for e in entries:
        img_path = img_dir / e["file"]
        if not img_path.exists():
            missing += 1
            continue
        items.append(
            {
                "file": e["file"],
                "method": e.get("method"),
                "name": e.get("name"),
                "template_id": e.get("template_id"),
                "strategy_type": e.get("strategy_type"),
                "headline": e.get("headline"),
                "body": e.get("body"),
                "cta": e.get("cta"),
                "img": _data_uri(img_path),
                "prefill": prefill_by_file.get(e["file"]),
            }
        )

    audit = bool(prefill_by_file)
    meta = {"dir": str(img_dir), "method": manifest.get("method"), "count": len(items), "audit": audit}
    # </script> 조기종료·XSS 방지용으로 '<'를 유니코드 이스케이프
    data_json = json.dumps(items, ensure_ascii=False).replace("<", "\\u003c")
    meta_json = json.dumps(meta, ensure_ascii=False).replace("<", "\\u003c")
    title = f"검수 — {img_dir.name} ({len(items)}장)"

    mode = "감사(VLM 프리필)" if audit else "백지"
    header_text = (
        f"{img_dir}  ·  {len(items)}장  ·  method={manifest.get('method') or '?'}  ·  {mode} 모드"
    )
    page = (
        _HTML.replace("__DATA__", data_json)
        .replace("__META__", meta_json)
        .replace("__HEADER__", html.escape(header_text))
        .replace("__TITLE__", title)
    )

    out_path = Path(args.out) if args.out else img_dir / "review.html"
    out_path.write_text(page, encoding="utf-8")

    size_mb = out_path.stat().st_size / 1_048_576
    print(f"검수 시트 생성 - {out_path}  (이미지 {len(items)}장, {size_mb:.1f}MB, {mode} 모드)")
    if audit:
        print(f"  VLM 프리필 적용 - {vlm_path.name}에서 {len(prefill_by_file)}장 판정 로드")
    else:
        print("  프리필 없음 — text_accuracy.csv가 없거나 --no-prefill. 먼저 measure_text_accuracy 실행 권장")
    if missing:
        print(f"  경고 - 디스크에 없는 이미지 {missing}장 제외됨")
    print("브라우저로 열어 검수 → 'CSV 저장' → review_by_human.csv")
    print("  같은 스키마라 measure_text_accuracy.py의 text_accuracy.csv와 나란히 비교 가능")


if __name__ == "__main__":
    main()
