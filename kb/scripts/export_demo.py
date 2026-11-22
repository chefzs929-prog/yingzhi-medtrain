#!/usr/bin/env python3
"""生成自包含演示页：把数据、样式与检索逻辑内联成一个 HTML。

输出：outputs/kb-demo.html
图片使用相对路径 deepworks-kb-import/images/...
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_sign_image_demo  # noqa: E402
import kbsearch  # noqa: E402
OUT = ROOT.parent / "outputs" / "kb-demo.html"


def load(name):
    return [json.loads(l) for l in (ROOT / "data" / name).read_text(encoding="utf8").splitlines() if l.strip()]


def main():
    sources = {s["id"]: s for s in json.loads((ROOT / "data" / "sources.json").read_text(encoding="utf8"))["sources"]}
    signs = load("signs.jsonl")
    standards = load("standards.jsonl")
    cases = load("cases.jsonl")
    guidelines = load("guidelines.jsonl")
    groups = load("groups.jsonl")

    docs = []
    for s in signs:
        s = dict(s)
        s["type"] = "sign"
        s["sources"] = [sources[i] for i in s.get("sources", []) if i in sources]
        docs.append(s)
    for s in standards:
        s = dict(s)
        s["type"] = "standard"
        s["url"] = s["official_url"]
        docs.append(s)
    for g in guidelines:
        g = dict(g)
        g["type"] = "guideline"
        docs.append(g)
    for c in cases:
        c = dict(c)
        c["type"] = "case"
        if isinstance(c.get("modality"), str):
            c["modality"] = [c["modality"]]
        c["image"] = "deepworks-kb-import/" + c["image"]
        docs.append(c)

    tax_path = ROOT / "data" / "taxonomy.json"
    taxonomy = json.loads(tax_path.read_text(encoding="utf8")) if tax_path.exists() else {"regions": []}
    data = {
        "docs": docs,
        "groups": groups,
        "taxonomy": taxonomy,
        "stats": {
            "signs": len(signs), "standards": len(standards),
            "cases": len(cases), "guidelines": len(guidelines),
            "sources": len(sources), "built_at": "2026-11-15",
            "regions": len(taxonomy.get("regions", [])), "conditions": len(groups),
        },
    }

    link_data = build_sign_image_demo.build_data(kbsearch.KB())
    link_imgs = {k: "deepworks-kb-import/" + v["image"] for k, v in link_data["images"].items()}
    link_js = (ROOT / "web" / "sign-image-demo.js").read_text(encoding="utf8")
    link_boot = (
        "<script>window.__DATA__=" + json.dumps(link_data, ensure_ascii=False).replace("</", "<\\/")
        + "; window.__IMG__=" + json.dumps(link_imgs, ensure_ascii=False) + ";</script>\n"
        + "<script>\n" + link_js + "\n</script>"
    )

    html = (ROOT / "web" / "index.html").read_text(encoding="utf8")
    css = (ROOT / "web" / "styles.css").read_text(encoding="utf8")
    html = html.replace('<link rel="stylesheet" href="styles.css">', "<style>\n" + css + "\n</style>")
    html = html.replace('<script src="app.js"></script>',
                        "<script>window.__KB__=" + json.dumps(data, ensure_ascii=False) + ";</script>\n<script>\n" + DEMO_JS + "\n</script>\n" + link_boot)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf8")
    print("demo ->", OUT, f"{OUT.stat().st_size/1024:.0f} KB")


DEMO_JS = r"""
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ALL = window.__KB__.docs;
const SIGNS = ALL.filter((d) => d.type === "sign");
const STDS = ALL.filter((d) => d.type === "standard");
const CASES = ALL.filter((d) => d.type === "case");
const GUIDES = ALL.filter((d) => d.type === "guideline");
const GROUPS = window.__KB__.groups || [];
const STATS = window.__KB__.stats;
const state = { q: "", modality: "", part: "", region: "", cond: "" };

const PART_HINTS = { "肺": "肺", "胸部": "胸", "胸膜": "胸膜", "纵隔": "纵隔", "心脏": "心脏", "乳腺": "乳腺", "甲状腺": "甲状腺", "肝": "肝", "胆": "胆", "胰": "胰", "肾": "肾", "脑": "脑", "头颅": "脑", "膝": "膝", "关节": "关节", "腹": "腹", "肠": "肠", "骨": "骨" };
const MOD_HINTS = { "ct": "CT", "mr": "MR", "磁共振": "MR", "核磁": "MR", "超声": "US", "b超": "US", "钼靶": "MG", "x线": "CR", "x光": "CR", "胸片": "CR", "dr": "CR" };
const FAMILY = { "肺": ["肺", "胸"], "胸部": ["肺", "胸"], "胸膜": ["胸膜", "胸"], "脑": ["脑", "头颅"], "头颅": ["脑", "头颅"], "膝": ["膝", "关节"], "关节": ["膝", "关节"], "腹": ["腹", "肠", "肝", "胆", "胰", "肾"], "肝": ["肝", "腹"], "胆": ["胆", "腹"], "胰": ["胰", "腹"], "肾": ["肾", "腹"], "肠": ["肠", "腹"] };
const same = (a, b) => !!a && !!b && (FAMILY[a] || [a]).some((x) => (FAMILY[b] || [b]).includes(x));
const grams = (s) => { const t = String(s).toLowerCase().replace(/[^\u4e00-\u9fffa-z0-9]/g, ""); const o = []; for (let i = 0; i < t.length - 1; i++) o.push(t.slice(i, i + 2)); return o; };
const textOf = (d) => [d.name, d.en, (d.aliases || []).join(" "), d.body_part, (d.modality || []).join(" "), (d.tags || []).join(" "), d.appearance, (d.may_see_in || []).join(" "), d.title, d.description_public, d.teaching_note, d.purpose, (d.dimensions || []).join(" ")].filter(Boolean).join(" ");

function scoreDoc(d, q, qg) {
  const ql = q.toLowerCase();
  let s = 0;
  if (d.type === "sign") {
    if (ql.includes(d.name.toLowerCase())) s += 24;
    if (d.en && ql.includes(d.en.toLowerCase())) s += 10;
    (d.aliases || []).forEach((a) => { if (ql.includes(a.toLowerCase())) s += 8; });
    if (d.body_part && ql.includes(d.body_part)) s += 5;
    (d.tags || []).forEach((t) => { if (ql.includes(t)) s += 2; });
  } else if (d.type === "standard") {
    if (ql.includes(d.name.toLowerCase())) s += 10;
    if (ql.includes((d.full_name || "").toLowerCase())) s += 6;
    if (d.body_part && ql.includes(d.body_part)) s += 4;
  } else if (d.type === "guideline") {
    if (d.standard_name && ql.includes(d.standard_name.toLowerCase())) s += 6;
    if (d.category && ql.includes(d.category.toLowerCase())) s += 8;
    (d.keywords || []).forEach((k) => { if (ql.includes(String(k).toLowerCase())) s += 3; });
  } else {
    if (ql.includes(d.title.toLowerCase())) s += 8;
    if (d.body_part && ql.includes(d.body_part)) s += 4;
  }
  const tg = new Set(grams(textOf(d)));
  qg.forEach((g) => { if (tg.has(g)) s += 0.7; });
  const parts = Object.keys(PART_HINTS).filter((k) => ql.includes(k)).map((k) => PART_HINTS[k]);
  if (parts.length && parts.some((p) => (d.body_part || "").includes(p))) s *= 1.5;
  const mods = Object.keys(MOD_HINTS).filter((k) => ql.includes(k)).map((k) => MOD_HINTS[k]);
  if (mods.length && (d.modality || []).some((m) => mods.includes(m))) s *= 1.3;
  return s;
}

function rank(q) {
  const qg = grams(q);
  let signs = [], stds = [], cases = [];
  if (!q) return { signs, stds, cases };
  const wp = Object.keys(PART_HINTS).filter((k) => q.toLowerCase().includes(k)).map((k) => PART_HINTS[k]);
  signs = SIGNS.map((d) => [scoreDoc(d, q, qg), d]).filter(([s]) => s > 2)
    .filter(([, d]) => !state.modality || (d.modality || []).includes(state.modality))
    .filter(([, d]) => !state.part || (d.body_part || "").includes(state.part))
    .filter(([, d]) => !wp.length || wp.some((p) => (d.body_part || "").includes(p)) || (d.body_part || "") === "全身")
    .sort((a, b) => b[0] - a[0]).slice(0, 6);
  const top = signs[0];
  stds = STDS.map((d) => [scoreDoc(d, q, qg) + (top && same(d.body_part, top[1].body_part) ? 6 : 0), d])
    .filter(([s, d]) => top && same(d.body_part, top[1].body_part))
    .sort((a, b) => b[0] - a[0]).slice(0, 2);
  if (top) {
    const t = top[1];
    cases = CASES.filter((c) => (c.sign_tags || []).includes(t.id) ||
      (same(c.body_part, t.body_part) && (c.modality || []).some((m) => (t.modality || []).includes(m)))).slice(0, 6);
    if (!cases.length) {
      cases = CASES.filter((c) => same(c.body_part, t.body_part) && (c.modality || []).some((m) => (t.modality || []).includes(m))).slice(0, 6);
    }
  }
  return { signs, stds, cases };
}

function search() {
  const q = (state.q || "").trim();
  const { signs, stds, cases } = rank(q);
  const n = signs.length + stds.length + cases.length;
  $("#meta").textContent = q ? `命中 ${n} 项 · 离线演示` : "输入关键词开始检索";
  $("#signs").innerHTML = signs.map(([s, d]) => signCard(d)).join("");
  $("#empty").hidden = n > 0;
  const conf = $("#confidence");
  if (!q || !n) { conf.hidden = true; }
  else {
    const top = signs.length ? signs[0][0] : 0;
    const level = top >= 24 ? "high" : top >= 12 ? "medium" : "low";
    conf.hidden = false;
    conf.className = "confidence " + level;
    conf.textContent = level === "high" ? "已匹配到直接相关的征象条目。以下为描述性解释与公开出处，不构成诊断意见。"
      : level === "medium" ? "匹配度一般：以下为相近条目，请核对定义与适用部位后再参考。"
      : "未找到直接对应条目：以下仅为字面相近内容，请勿据此推断，建议改用标准影像学术语。";
  }
  $("#standards").innerHTML = stds.length ? `<div class="panel"><h2>相关公开标准</h2>${stds.map(([, d]) => stdCard(d)).join("")}</div>` : "";
  const rel = signs.length ? related(signs[0][1]) : [];
  $("#related").innerHTML = rel.length ? `<div class="panel"><h2>相关征象</h2><div class="rel-list">${rel.map((x) => `<button class="rel" data-q="${esc(x.name)}">${esc(x.name)}<small>${esc((x.modality || []).join("/"))}</small></button>`).join("")}</div></div>` : "";
  $$("#related .rel").forEach((b) => b.addEventListener("click", () => { $("#q").value = b.dataset.q; state.q = b.dataset.q; search(); }));
  $("#casesWrap").hidden = !cases.length;
  $("#cases").innerHTML = cases.map((c) => imgCard(c)).join("");
}

function related(me) {
  const mt = new Set(me.tags || []);
  return SIGNS.filter((d) => d.id !== me.id).map((d) => {
    let s = 0; (d.tags || []).forEach((t) => { if (mt.has(t)) s += 2; });
    if (d.body_part === me.body_part) s += 1;
    if ((d.modality || []).some((m) => (me.modality || []).includes(m))) s += 0.5;
    return [s, d];
  }).filter(([s]) => s > 0).sort((a, b) => b[0] - a[0]).slice(0, 4).map(([, d]) => d);
}

function signCard(s) {
  const mods = (s.modality || []).map((m) => `<span class="tag mod">${esc(m)}</span>`).join("");
  const src = (s.sources || []).map((x) => `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title || x.id)}</a>`).join("");
  const note = (s.sources || []).map((x) => x.license_note).filter(Boolean).slice(0, 1).map(esc).join("");
  const lk = ((window.__DATA__ && window.__DATA__.signs) || []).find((x) => x.id === s.id);
  return `<article class="card"><div class="card-head"><h3>${esc(s.name)}</h3><span class="en">${esc(s.en)}</span></div>
    <div class="tags">${mods}${s.body_part ? `<span class="tag">${esc(s.body_part)}</span>` : ""}</div>
    <p>${esc(s.appearance)}</p><div class="label">影像上可见于</div>
    <div class="pills">${(s.may_see_in || []).map((x) => `<span class="pill">${esc(x)}</span>`).join("")}</div>
    ${(s.pitfalls || []).length ? `<div class="caution"><b>易混淆 / 判读注意</b>${s.pitfalls.map(esc).join("；")}</div>` : ""}
    <div class="sources">来源：${src || "—"}${note ? `<span class="src-note">${note}</span>` : ""}</div>
    ${lk ? `<div class="card-actions"><button type="button" class="btn ghost" data-link-sign="${esc(s.id)}">图文对照 · ${lk.links.length} 处</button></div>` : ""}</article>`;
}

function stdCard(x) {
  return `<div class="std"><h4>${esc(x.name)}</h4><div class="pub">${esc(x.publisher)} · ${esc(x.body_part || "")}</div>
    <p class="muted small">${esc(x.purpose)}</p>
    <ul>${(x.dimensions || []).slice(0, 4).map((d) => `<li>${esc(d)}</li>`).join("")}</ul>
    <div class="sources"><a href="${esc(x.url)}" target="_blank" rel="noopener">标准入口</a><span class="src-note">${esc(x.license_note || "仅链接引用")}</span></div></div>`;
}

function imgCard(c) {
  const lc = ((window.__DATA__ && Object.values(window.__DATA__.links)) || []).filter((x) => x.image.id === c.id).length;
  return `<div class="img-card" data-id="${esc(c.id)}"><div class="thumb"><img loading="lazy" src="${esc(c.image)}" alt="${esc(c.title)}"></div>
    <div class="cap"><b>${esc(c.title)}${lc ? `<span class="link-badge">图文 ${lc}</span>` : ""}</b><span>${esc((c.modality || []).join("/"))} · ${esc(c.body_part)} · ${esc(c.license)}</span></div></div>`;
}

function openCase(c) {
  $("#lbImg").src = c.image; $("#lbImg").alt = c.title;
  $("#lbTitle").textContent = c.title;
  $("#lbDesc").textContent = [c.description_public, c.teaching_note].filter(Boolean).join(" ");
  const lks = window.__DATA__ ? [...new Set(Object.values(window.__DATA__.links).filter((x) => x.image.id === c.id).map((x) => x.sign_id))] : [];
  $("#lbLinks").innerHTML = lks.map((id) => { const s = window.__DATA__.signs.find((x) => x.id === id); return s ? `<button type="button" data-link-sign="${esc(s.id)}">${esc(s.name)}</button>` : ""; }).join("");
  $("#lbCredit").textContent = `许可：${c.license} · 作者：${c.artist} · 已核验无患者标识`;
  $("#lbLink").href = c.source_page;
  $("#lightbox").showModal();
}

document.addEventListener("click", (e) => {
  const linkBtn = e.target.closest("[data-link-sign]");
  if (linkBtn) {
    e.preventDefault();
    e.stopPropagation();
    showView("links");
    const chip = document.querySelector(`#linksPicker [data-sign="${linkBtn.dataset.linkSign}"]`);
    if (chip) chip.click();
    return;
  }
  const card = e.target.closest(".img-card");
  if (!card) return;
  const c = CASES.find((x) => x.id === card.dataset.id);
  if (c) openCase(c);
});
$("#closeLb").addEventListener("click", () => $("#lightbox").close());
$("#lightbox").addEventListener("click", (e) => { if (e.target === $("#lightbox")) $("#lightbox").close(); });

function showView(name) {
  ["search", "links", "dual", "images", "about"].forEach((v) => { $("#view-" + v).hidden = v !== name; });
  $$("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  if (name === "images") renderGallery();
  if (name === "about") renderStats();
  window.scrollTo({ top: 0, behavior: "smooth" });
}
$$("#tabs button").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));
$$("[data-view-link]").forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); showView(a.dataset.viewLink); }));

$("#searchForm").addEventListener("submit", (e) => { e.preventDefault(); state.q = $("#q").value; search(); });
$("#chips").addEventListener("click", (e) => { const b = e.target.closest("button[data-q]"); if (!b) return; $("#q").value = b.dataset.q; state.q = b.dataset.q; search(); });
["#modality", "#part"].forEach((sel) => $(sel).addEventListener("change", () => { state.modality = $("#modality").value; state.part = $("#part").value; if (state.q) search(); }));


/* ---------------- dual line ---------------- */
const DFLOW = /已完成|完成超声|完成多参数|完成初始|具备五个维度|属于筛查人群|属于高危人群|有可比较|测量方法一致|评估主胰管|信息不足|偶然发现/;
const DSTD = [["STD-TIRADS", ["ti-rads", "tirads", "甲状腺"]], ["STD-BIRADS", ["bi-rads", "birads", "乳腺"]],
  ["STD-LIRADS", ["li-rads", "lirads", "肝"]], ["STD-BOSNIAK", ["bosniak", "肾"]],
  ["STD-PIRADS", ["pi-rads", "pirads", "前列腺"]], ["STD-ORADS", ["o-rads", "orads", "卵巢"]],
  ["STD-LUNGRADS", ["lung-rads", "lungrads", "筛查"]], ["STD-FLEISCHNER", ["fleischner"]]];

function dMM(v, u) { return (u === "cm" || u === "厘米") ? v * 10 : v; }
function dNums(t) {
  const out = []; let m;
  let re = /(\d+(?:\.\d+)?)\s*(?:—|－|-|~|至)\s*(\d+(?:\.\d+)?)\s*(mm|cm|毫米|厘米)/g;
  while ((m = re.exec(t))) out.push({ k: "range", lo: dMM(+m[1], m[3]), hi: dMM(+m[2], m[3]) });
  re = /(≥|<=|≤|<|>)\s*(\d+(?:\.\d+)?)\s*(mm|cm|毫米|厘米)/g;
  while ((m = re.exec(t))) out.push({ k: "op", op: m[1], v: dMM(+m[2], m[3]) });
  re = /(\d+(?:\.\d+)?)\s*(mm|cm|毫米|厘米)/g;
  while ((m = re.exec(t))) out.push({ k: "val", v: dMM(+m[1], m[2]) });
  return out;
}
function dCore(t) {
  const out = new Set(); let m;
  let re = /TR\s*([1-5])/gi; while ((m = re.exec(t))) out.add(m[1]);
  re = /BI-?RADS\s*([0-6])/gi; while ((m = re.exec(t))) out.add(m[1]);
  re = /LR-?\s*([1-5])/gi; while ((m = re.exec(t))) out.add(m[1]);
  re = /Bosniak\s*(IIF|I{1,3}|IV)/gi; while ((m = re.exec(t))) out.add(m[1].toUpperCase());
  re = /PI-?RADS\s*([1-5])/gi; while ((m = re.exec(t))) out.add(m[1]);
  re = /O-?RADS\s*([0-5])/gi; while ((m = re.exec(t))) out.add(m[1]);
  re = /(IIF|IV|III|II|I)\s*类/g; while ((m = re.exec(t))) out.add(m[1].toUpperCase());
  re = /([0-6])\s*类/g; while ((m = re.exec(t))) out.add(m[1]);
  re = /类别\s*([1-4])X?/g; while ((m = re.exec(t))) out.add(m[1]);
  return out;
}
function dStd(q) {
  const ql = q.toLowerCase();
  for (const [sid, keys] of DSTD) if (keys.some((k) => ql.includes(k))) return sid;
  return null;
}
function dSyn(t) { return t.replace(/囊肿/g, "囊性").replace(/囊性病变/g, "囊性"); }
function dB(t) { const x = dSyn(String(t).toLowerCase()).replace(/[^\u4e00-\u9fffa-z0-9]/g, ""); const o = new Set(); for (let i = 0; i < x.length - 1; i++) o.add(x.slice(i, i + 2)); return o; }
function dCond(cond, q, qc, qn, g, qs) {
  if (cond.includes("部分实性") && !q.includes("部分")) return false;
  if (cond.includes("磨玻璃") && !q.includes("磨玻璃")) return false;
  if (cond.includes("单发") && q.includes("多发")) return false;
  if (cond.includes("分类") && g) {
    const gc = dCore(g.category), q2 = dCore(q);
    const sameStd = !qs || qs === g.standard_id;
    if (gc.size && q2.size && sameStd && [...gc].some((x) => q2.has(x))) return true;
    if (gc.size && !q2.size) return false;
  }
  const cn = dNums(cond);
  if (cn.length) {
    if (!qn.length) return false;
    for (const c of cn) {
      if (c.k === "range") {
        if (qn.some((n) => n.k === "val" && n.v >= c.lo && n.v <= c.hi)) return true;
        if (qn.some((n) => n.k === "op" && n.v >= c.lo && n.v <= c.hi)) return true;
      } else if (c.k === "op") {
        for (const n of qn) {
          const v = n.k === "val" ? n.v : (n.k === "op" ? n.v : null);
          if (v == null) continue;
          if (c.op === "≥" && v >= c.v) return true;
          if ((c.op === "≤" || c.op === "<=") && v <= c.v) return true;
          if (c.op === "<" && v < c.v) return true;
          if (c.op === ">" && v > c.v) return true;
        }
      }
    }
    return false;
  }
  const cg = dB(cond), qg = dB(q);
  if (!cg.size) return false;
  const inter = [...cg].filter((x) => qg.has(x)).length;
  if (inter / cg.size >= 0.6) return true;
  if (cond.length <= 4 && inter > 0) return true;
  return false;
}
function assessLocal(q) {
  const r = rank(q);
  let signs = r.signs.map((x) => x[1]);
  const top = signs[0];
  if (top) {
    const samep = signs.filter((x) => same(x.body_part, top.body_part));
    signs = (samep.length ? samep : signs).slice(0, 3);
  }
  const qc = dCore(q), qn = dNums(q), qs = dStd(q);
  const pool = GUIDES.filter((g) => !top || same(g.body_part, top.body_part));
  const cands = pool.map((g) => {
    const conds = (g.conditions || []).filter((c) => !DFLOW.test(c));
    const matched = conds.filter((c) => dCond(c, q, qc, qn, g, qs));
    const missing = conds.filter((c) => !matched.includes(c));
    return { g, matched, missing, cov: conds.length ? matched.length / conds.length : 0, sc: scoreDoc(g, q, grams(q)) };
  }).sort((a, b) => (b.cov - a.cov) || (b.sc - a.sc));

  let best = cands.find((x) => x.cov > 0) || null;
  if (!best && cands.length) {
    const withCat = cands.filter((x) => dCore(x.g.category).size);
    best = (withCat.length ? withCat : cands)[0];
    const miss = [];
    if (dCore(best.g.category).size && !dCore(q).size) miss.push("分类等级（" + best.g.standard_name + "）");
    if ((best.g.conditions || []).some((c) => dNums(c).length) && !qn.length) miss.push("病灶尺寸");
    best.missing = miss.length ? miss : ["条款适用条件"];
    best.matched = [];
    best.cov = 0;
  }

  let level, note;
  if (!signs.length && !cands.length) { level = "insufficient"; note = "影像线与指南线都未命中，库内没有可对照的证据。"; }
  else if (!signs.length) { level = "insufficient"; note = "影像线未命中征象条目，无法与指南条款建立对应关系。"; best = null; }
  else if (!cands.length) { level = "insufficient"; note = "指南线未命中同部位条款，暂不做对应判断。"; best = null; }
  else if (best.cov >= 1) { level = "aligned"; note = "影像线已覆盖该条款的全部适用条件，两线在描述维度上对应。条款的处理方向仅为原文摘录，不构成对你的建议。"; }
  else if (best.cov > 0) { level = "partial"; note = "指南线缺少关键条件，尚不能定位到具体条款。需补充：" + best.missing.join("、") + "。"; }
  else { level = "partial"; note = "影像线已命中征象，但指南线缺少定位条件。需补充：" + best.missing.join("、") + "。"; }

  const order = best ? [best.g, ...cands.filter((x) => x !== best).map((x) => x.g)] : [];
  return {
    query: q,
    imaging: { signs, cases: r.cases, confidence: "high" },
    guidelines: order.slice(0, 6),
    alignment: {
      level, coverage: best ? Math.round(best.cov * 100) / 100 : 0,
      best_id: best ? best.g.id : null, matched: best ? best.matched : [], missing: best ? best.missing : [],
      note, action: best ? best.g.action : "",
      action_source: "处理方向摘自公开条款摘要，仅供对照，不是本工具给出的建议。",
      divergent: [],
    },
    disclaimer: "双线判断表示库内影像证据与指南条款的对齐情况，不构成诊断意见，也不替代临床决策。",
  };
}

function glCard(g, a) {
  const isBest = g.id === a.best_id;
  const conds = (g.conditions || []).map((c) => {
    let cls = "pre";
    if (isBest) { if ((a.matched || []).includes(c)) cls = "ok"; else if ((a.missing || []).includes(c)) cls = "miss"; }
    return `<span class="cond ${cls}">${esc(c)}</span>`;
  }).join("");
  return `<div class="gl ${isBest ? "best" : ""}">
    <div class="gl-head"><b>${esc(g.id)}</b><span class="tag">${esc(g.category)}</span><span class="pub">${esc(g.standard_name)} · ${esc(g.version_year)}</span></div>
    <p>${esc(g.statement)}</p><div class="cond-row">${conds}</div>
    <div class="gl-action">条款方向：<span>${esc(g.action)}</span></div>
    <div class="sources"><a href="${esc(g.source_url)}" target="_blank" rel="noopener">标准入口</a><span class="src-note">${esc(g.license_note)}</span></div>
  </div>`;
}

function renderDual(d) {
  const a = d.alignment;
  const box = $("#dualAlign");
  box.hidden = false;
  box.className = "align " + a.level;
  const label = { aligned: "两线对齐", partial: "条件不足", insufficient: "无法对照" }[a.level] || a.level;
  box.innerHTML = `<div class="align-head"><span class="badge ${a.level}">${label}</span>
    <span class="cov">条件覆盖 ${Math.round((a.coverage || 0) * 100)}%</span>
    ${a.best_id ? `<span class="cov">对应条款 ${esc(a.best_id)}</span>` : ""}</div>
    <p>${esc(a.note)}</p>
    ${a.action ? `<div class="align-action"><b>条款方向</b><span>${esc(a.action)}</span><small>${esc(a.action_source)}</small></div>` : ""}
    <div class="cond-row">${(a.matched || []).map((c) => `<span class="cond ok">已覆盖 · ${esc(c)}</span>`).join("")}${(a.missing || []).map((c) => `<span class="cond miss">待补充 · ${esc(c)}</span>`).join("")}</div>
    <p class="muted small">${esc(d.disclaimer)}</p>`;
  $("#dualImaging").innerHTML = d.imaging.signs.length ? d.imaging.signs.map((s) => `<div class="mini">
    <div class="card-head"><h3>${esc(s.name)}</h3><span class="en">${esc(s.en)}</span></div><p>${esc(s.appearance)}</p>
    <div class="pills">${(s.may_see_in || []).slice(0, 4).map((x) => `<span class="pill">${esc(x)}</span>`).join("")}</div>
    <div class="sources">来源：${(s.sources || []).map((x) => `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title || x.id)}</a>`).join("")}</div></div>`).join("")
    : `<p class="muted">影像线未命中征象条目。</p>`;
  $("#dualGuide").innerHTML = d.guidelines.length ? d.guidelines.map((g) => glCard(g, a)).join("") : `<p class="muted">指南线未命中同部位条款。</p>`;
  $("#dualCasesWrap").hidden = !d.imaging.cases.length;
  $("#dualCases").innerHTML = d.imaging.cases.map(imgCard).join("");
  $("#dualMeta").textContent = `影像 ${d.imaging.signs.length} 条 · 条款 ${d.guidelines.length} 条 · 离线演示`;
}

$("#dualForm").addEventListener("submit", (e) => { e.preventDefault(); const q = $("#dq").value.trim(); if (q) renderDual(assessLocal(q)); });
$("#dualChips").addEventListener("click", (e) => { const b = e.target.closest("button[data-q]"); if (!b) return; $("#dq").value = b.dataset.q; renderDual(assessLocal(b.dataset.q)); });

const TAX = window.__KB__.taxonomy || { regions: [] };
const REG_ORDER = {};
TAX.regions.forEach((r, i) => { REG_ORDER[r.id] = i; });
const ALL_CONDS = () => TAX.regions.reduce((a, r) => a.concat(r.conditions || []), []);

function renderTabs() {
  $("#regionTabs").innerHTML = [{ id: "", name: "全部部位", count: CASES.length }].concat(TAX.regions)
    .map((r) => `<button class="chip${state.region === r.id ? " on" : ""}" data-region="${esc(r.id)}">${esc(r.name)}<em>${r.count}</em></button>`).join("");
  const cur = TAX.regions.find((r) => r.id === state.region);
  const conds = cur ? (cur.conditions || []) : ALL_CONDS();
  $("#condChips").innerHTML = `<button class="chip${state.cond === "" ? " on" : ""}" data-cond="">全部病症</button>` +
    conds.map((c) => `<button class="chip${state.cond === c.id ? " on" : ""}${c.has_images ? "" : " empty"}" data-cond="${esc(c.id)}">${esc(c.name)}<em>${c.count}</em></button>`).join("");
}

function renderGallery() {
  renderTabs();
  const m = $("#imgModality").value;
  const list = GROUPS.map((g) => ({
    ...g,
    items: CASES.filter((c) => c.group_id === g.id && (!m || (c.modality || []).includes(m))),
  }))
    .filter((g) => g.items.length)
    .filter((g) => !state.region || g.region_id === state.region)
    .filter((g) => !state.cond || g.id === state.cond)
    .sort((a, b) => (REG_ORDER[a.region_id] ?? 9) - (REG_ORDER[b.region_id] ?? 9) || b.items.length - a.items.length);
  const total = list.reduce((n, g) => n + g.items.length, 0);
  const rn = state.region ? ((TAX.regions.find((r) => r.id === state.region) || {}).name || "") : "";
  $("#imgMeta").textContent = `${rn ? rn + " · " : ""}${list.length} 个病症分类 · ${total} 张公开影像`;
  $("#gallery").innerHTML = list.map((g) => `<section class="group">
    <div class="group-head">
      <div class="group-title"><span class="reg-tag">${esc(g.region_name || "")}</span><h3>${esc(g.name)}</h3><span class="meta">${g.items.length} 张 · ${(g.modality || []).join("/")} · ${esc(g.body_part)}</span></div>
      <p>${esc(g.description)}</p><p class="small muted">${esc(g.criteria)}</p>
    </div>
    <div class="images">${g.items.map(imgCard).join("")}</div>
    <p class="group-caution">${esc(g.caution)}</p>
  </section>`).join("") || `<p class="muted">该筛选条件下暂无已核验影像。</p>`;
}
$("#imgModality").addEventListener("change", renderGallery);
$("#regionTabs").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-region]"); if (!b) return;
  state.region = b.dataset.region; state.cond = "";
  renderTabs(); renderGallery();
});
$("#condChips").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-cond]"); if (!b) return;
  state.cond = b.dataset.cond;
  renderTabs(); renderGallery();
  const c = ALL_CONDS().find((x) => x.id === state.cond);
  if (c && c.search_query) $("#simQ").value = c.search_query;
});
$("#simBtn").addEventListener("click", () => {
  $("#simMeta").textContent = "离线单文件不联网：用 python3 kb/scripts/serve.py --port 4180 打开服务版即可调用该接口";
  $("#simProviders").innerHTML = "";
  $("#simResults").innerHTML = "";
});
["#imgModality", "#imgPart"].forEach((sel) => $(sel).addEventListener("change", renderGallery));
$("#gallery").addEventListener("click", (e) => {
  const card = e.target.closest(".img-card"); if (!card) return;
  const c = CASES.find((x) => x.id === card.dataset.id); if (!c) return;
  $("#refViewer").innerHTML = `<img src="${esc(c.image)}" alt="${esc(c.title)}">`;
  $("#refMeta").textContent = `${c.title} · ${c.license} · ${c.artist}`;
});
$("#localFile").addEventListener("change", (e) => {
  const f = e.target.files && e.target.files[0]; if (!f) return;
  $("#localViewer").innerHTML = `<img src="${URL.createObjectURL(f)}" alt="本地图像预览">`;
});

function renderStats() {
  const items = [["征象条目", STATS.signs], ["公开标准", STATS.standards], ["部位 / 病症", `${STATS.regions} / ${STATS.conditions}`], ["指南条款", STATS.guidelines], ["公开影像", STATS.cases]];
  $("#aboutStats").innerHTML = items.map(([k, v]) => `<div class="stat"><b>${v}</b><span>${k}</span></div>`).join("");
}
$("#footStats").textContent = `${STATS.signs} 条征象 · ${STATS.guidelines} 条指南条款 · ${STATS.cases} 张公开影像`;
renderStats();
$("#q").value = "磨玻璃影"; state.q = "磨玻璃影"; search();
"""


if __name__ == "__main__":
    main()
