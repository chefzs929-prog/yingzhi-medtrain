#!/usr/bin/env python3
"""导出可导入 DeepWorks 知识库的资产包。

输出：outputs/deepworks-kb-import/
- kb-import.jsonl   每条一行，含 title / content / metadata
- kb-signs.md       征象条目（按标题分节，适合文档导入）
- kb-standards.md   公开标准摘要
- kb-cases.md       公开影像条目（含相对图片路径）
- kb-sign-links.md  征象文字片段 ↔ 影像区域关联（v1）
- sign_links.jsonl  图文关联原始数据
- images/           已核验的公开影像
- ATTRIBUTION.md    署名与许可
- README.md         导入与验证说明
"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT.parent / "outputs" / "deepworks-kb-import"
VER = "2026-11-15"


README_TEXT = """# 影像征象与指南双线知识库 · 导入包

面向影像教学的知识库资产：{{SIGNS}} 条征象条目、{{STD}} 个公开标准、{{GL}} 条指南条款、{{CASES}} 张已核验的公开许可影像、{{LINKS}} 条图文关联，按 **{{REGIONS}} 个部位（一级）→ {{CONDS}} 个病症分类（二级）** 归类。
所有内容只做**描述性解释、条款对照与出处定位**，不输出临床结论。

- 版本：2026-11-15
- 记录数：{{TOTAL}}（征象 {{SIGNS}} / 标准 {{STD}} / 指南条款 {{GL}} / 影像 {{CASES}} / 图文关联 {{LINKS}} / 病症分类 {{GROUPS}}）
- 分类层级：{{REGIONS}} 个部位 → {{CONDS}} 个病症分类（其中 {{CONDS_IMG}} 个已有影像）
- 来源：11 个公开来源，逐条登记在 `ATTRIBUTION.md` 与各条 metadata 中

## 目录

```
deepworks-kb-import/
├── kb-import.jsonl     {{TOTAL}} 条结构化记录（title / content / metadata）
├── kb-signs.md         征象条目合集
├── kb-standards.md     公开标准摘要
├── kb-guidelines.md    指南条款库（按标准分组）
├── kb-cases.md         公开影像条目（部位 → 病症两级，含相对图片路径）
├── kb-sign-links.md    {{LINKS}} 条征象文字 ↔ 影像区域关联
├── sign_links.jsonl    图文关联原始数据
├── images/             {{CASES}} 张公开许可影像
├── ATTRIBUTION.md      作者、许可、来源页与排除记录
└── README.md           本文件
```

## 导入步骤（以 DeepWorks 当前版本的入口为准）

1. **建三个知识库**，不要混成一个：
   - `KB-征象`：导入 `kb-signs.md`；如需图文对照，再导入 `kb-sign-links.md`
   - `KB-指南`：导入 `kb-guidelines.md` 与 `kb-standards.md`
   - `KB-影像`：导入 `kb-cases.md`，保持 `images/` 与文档的相对路径不变
2. **按条目切分**：`kb-signs.md`、`kb-guidelines.md` 用 `##` / `###`；`kb-cases.md` 用 `##`（一级部位）/ `###`（二级病症）/ `####`（单张影像）三级。每条 200—600 字，以标题为边界切分，不要按固定字数硬切。
3. **登记元数据**：按 `kb-import.jsonl` 的 metadata 映射 `type`、`id`、`standard_id`、`category`、`modality`、`body_part`、`region_id`、`group_id`、`version_year`、`license`、`source_url`、`not_for_diagnosis`。
4. **导入后跑验证问句**（见下表），确认双线召回与出处正确，再接入工作流。

## 验证问句

| 提问 | 期望召回 | 期望行为 |
| --- | --- | --- |
| 甲状腺结节 TR4 1.6cm | SIGN-058 + GL-TIRADS-03 + 甲状腺超声图 | 双线对齐：条款方向为原文摘录，不转述为建议 |
| 甲状腺低回声结节 | SIGN-058 + TI-RADS 条款候选 | 条件不足：提示补充分类等级 |
| 肺实性结节 7mm | SIGN-003 + GL-FLEISCHNER-02 + 胸部 CT | 双线对齐：6—12 个月复查为条款方向 |
| 肾囊肿 Bosniak IIF | SIGN-033 + GL-BOSNIAK-03 | 双线对齐：6 个月复查为条款方向 |
| 乳腺肿块 BI-RADS 4 伴毛刺 | SIGN-055 + GL-BIRADS-04 | 双线对齐：考虑活检为条款方向 |
| 儿童先天性心脏病超声分级 | 无直接条目 | 明确说明库内无依据 |
| 我这个结节是不是癌，要不要手术 | 无 | 拒答 + 非诊断声明 |

## 影像组一览

影像按表现与公开描述归为 11 组，同组不代表同一疾病：

| 组 | 内容 | 张数 |
| --- | --- | --- |
| 肺部实变与气腔影 | 肺炎、气腔影、肺不张 | 5 |
| 磨玻璃影与间质改变 | 磨玻璃、囊性间质改变 | 2 |
| 肺结节与肿块 | 孤立结节、钙化结节、粟粒样结节 | 2 |
| 胸腔积液与气胸 | 积液、气胸、正侧位对照 | 3 |
| 胸部 CT 窗位与层面 | 窗宽窗位与定位像 | 2 |
| 甲状腺结节 | 低回声、囊性、钙化 | 3 |
| 乳腺钙化与肿块 | 钼靶钙化、肿块、超声 | 6 |
| 头颅出血、梗死与占位 | 出血、梗死、囊性改变 | 3 |
| 腹部实质脏器 | 肝多发低密度灶 | 1 |
| 肌骨与脊柱 | 待补（Commons 限流） | 0 |
| 正常解剖对照 | 正常胸片、正常头颅 CT | 5 |

## 双线判断的语义

- **影像线**：库内命中的征象条目与公开影像，回答「影像上是什么表现、可见于什么情况」。
- **指南线**：库内命中的条款，回答「在什么适用条件下、公开条款给出什么方向」。
- **对齐判断**：只判断两条证据线是否对齐，并列出已覆盖与待补充的条件；条件不足时明确提示缺什么，不猜测。
- **不是临床判断**：条款方向仅为原文摘录，不构成对个体的建议。

## 边界与合规

- 所有条目的 `not_for_diagnosis` 均为 true，正文含固定边界声明。
- 标准与指南只给维度摘要与官方入口，不复制评分表、阈值与处理路径原文。
- 影像仅 CC0 / CC BY / CC BY-SA / 公有领域，已排除 NC、ND、人物照片与含年龄日期标记的图像，逐张人工核验。
- 可撤回：权利人提出异议时，删除对应文件与条目并重建索引。

## 重建方式

```bash
cd kb
python3 scripts/kbsearch.py build
python3 scripts/compliance_check.py
python3 -m unittest discover -s tests -t . -v
python3 scripts/export_kb.py
```

本地演示：`python3 scripts/serve.py --port 4180` → http://127.0.0.1:4180
"""


def load(name):
    return [json.loads(l) for l in (ROOT / "data" / name).read_text(encoding="utf8").splitlines() if l.strip()]


def main():
    signs = load("signs.jsonl")
    standards = load("standards.jsonl")
    cases = load("cases.jsonl")
    guidelines = load("guidelines.jsonl")
    links = load("sign_links.jsonl") if (ROOT / "data" / "sign_links.jsonl").exists() else []
    groups = load("groups.jsonl")
    sources = {s["id"]: s for s in json.loads((ROOT / "data" / "sources.json").read_text(encoding="utf8"))["sources"]}

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "images").mkdir(parents=True)
    for c in cases:
        src = ROOT / c["image"]
        shutil.copyfile(src, OUT / "images" / src.name)
    shutil.copyfile(ROOT / "licenses" / "ATTRIBUTION.md", OUT / "ATTRIBUTION.md")
    if (ROOT / "data" / "sign_links.jsonl").exists():
        shutil.copyfile(ROOT / "data" / "sign_links.jsonl", OUT / "sign_links.jsonl")

    records = []

    sign_md = ["# 影像征象条目（60 条）", "",
               "> 描述性教学摘要，不构成诊断意见；每条均标注公开来源。", ""]
    for s in signs:
        srcs = [sources[i] for i in s.get("sources", []) if i in sources]
        body = [
            f"模态：{'、'.join(s.get('modality', []))}",
            f"部位：{s.get('body_part', '')}",
            f"别名：{'、'.join(s.get('aliases', []))}",
            "",
            f"影像表现：{s['appearance']}",
            "",
            f"影像上可见于：{'；'.join(s.get('may_see_in', []))}",
            "",
            f"易混淆与判读注意：{'；'.join(s.get('pitfalls', []))}",
            "",
            "来源：" + "；".join(f"{x['publisher']}（{x['url']}）" for x in srcs),
            "",
            "边界：本条目为描述性教学摘要，不构成诊断意见，不对个体影像给出结论。",
        ]
        content = "\n".join(body)
        records.append({
            "title": f"征象｜{s['name']}（{s['en']}）",
            "content": content,
            "metadata": {
                "type": "sign", "id": s["id"], "modality": s.get("modality", []),
                "body_part": s.get("body_part", ""), "tags": s.get("tags", []),
                "source_ids": s.get("sources", []),
                "source_urls": [x["url"] for x in srcs],
                "kb_version": VER, "not_for_diagnosis": True,
            },
        })
        sign_md += [f"## {s['name']}（{s['en']}）", "", content, ""]

    std_md = ["# 公开标准与分类系统（8 个）", "",
              "> 仅做维度摘要与来源链接，不复制标准全文、评分表与阈值。", ""]
    for s in standards:
        content = "\n".join([
            f"发布方：{s['publisher']}",
            f"适用部位：{s.get('body_part', '')}",
            f"用途：{s['purpose']}",
            "",
            "分类维度：" + "；".join(s.get("dimensions", [])),
            "",
            f"报告形式：{s.get('report_form', '')}",
            "",
            f"官方入口：{s['official_url']}",
            f"版权说明：{s.get('license_note', '')}",
            "",
            "边界：具体条目、阈值与处理建议以官方当前版本为准；本库不对个体影像分类。",
        ])
        records.append({
            "title": f"标准｜{s['name']}（{s['full_name']}）",
            "content": content,
            "metadata": {
                "type": "standard", "id": s["id"], "publisher": s["publisher"],
                "body_part": s.get("body_part", ""), "source_urls": [s["official_url"]],
                "license": "仅链接引用", "kb_version": VER, "not_for_diagnosis": True,
            },
        })
        std_md += [f"## {s['name']} · {s['full_name']}", "", content, ""]

    gl_md = ["# 指南条款库（47 条）", "",
             "> 条款为自撰摘要，保留适用条件、方向、版本与官方入口；不复制受版权全文。", ""]
    cur = None
    for g in guidelines:
        if g["standard_id"] != cur:
            cur = g["standard_id"]
            gl_md += [f"## {g['standard_name']}（{g['version_year']}）", ""]
        content = "\n".join([
            f"类别：{g['category']}",
            f"章节：{g['section']}",
            f"适用部位：{g.get('body_part', '')}",
            "",
            f"条款摘要：{g['statement']}",
            "",
            "适用条件：" + "；".join(g.get("conditions", [])),
            f"条款方向：{g['action']}",
            f"推荐等级：{g.get('rec_level') or '未标注'}；证据等级：{g.get('evidence_level') or '未标注'}",
            f"版本：{g['version_year']}",
            "",
            f"官方入口：{g['source_url']}",
            f"版权说明：{g.get('license_note', '')}",
            "",
            "边界：条款摘要仅供对照，具体阈值与处理路径以官方原文为准；本库不对个体影像作出判断。",
        ])
        records.append({
            "title": f"指南｜{g['standard_name']} · {g['category']} · {g['id']}",
            "content": content,
            "metadata": {
                "type": "guideline", "id": g["id"], "standard_id": g["standard_id"],
                "category": g["category"], "body_part": g.get("body_part", ""),
                "version_year": g["version_year"], "status": g.get("status", "active"),
                "source_url": g["source_url"], "license": "摘要自撰，仅链接引用",
                "kb_version": VER, "not_for_diagnosis": True,
            },
        })
        gl_md += [f"### {g['id']} · {g['category']}", "", content, ""]

    tax = json.loads((ROOT / "data" / "taxonomy.json").read_text(encoding="utf8")) if (ROOT / "data" / "taxonomy.json").exists() else {"regions": []}
    gmap = {g["id"]: g for g in groups}
    case_md = ["# 公开影像对照（部位 → 病症两级归类）", "",
               "> 全部来自 Wikimedia Commons 公开许可素材，已逐张核验无患者标识。",
               "> 一级为解剖部位，二级为病症/征象族；同一分类按影像表现或公开描述归并，不代表同一疾病。", ""]
    for r in sorted(tax.get("regions", []), key=lambda x: x.get("order", 99)):
        rgroups = [(gmap[gid], [c for c in cases if c.get("group_id") == gid])
                   for gid in r.get("groups", []) if gid in gmap]
        rgroups = [(g, items) for g, items in rgroups if items]
        if not rgroups:
            continue
        rtotal = sum(len(items) for _, items in rgroups)
        case_md += [f"## 一级：{r['name']}（{rtotal} 张）", "", f"> {r.get('note', '')}", ""]
        for g, items in rgroups:
            case_md += [f"### 二级：{g['name']}（{len(items)} 张）", "",
                        f"> {g.get('description', '')}",
                        f"> {g.get('criteria', '') if str(g.get('criteria', '')).startswith('归类依据') else '归类依据：' + str(g.get('criteria', ''))}",
                        f"> 使用提醒：{g.get('caution', '')}", ""]
            for c in items:
                content = "\n".join([
                    f"部位：{r['name']}",
                    f"病症分类：{g['name']}",
                    f"模态：{'、'.join(c.get('modality', []))}",
                    f"具体部位：{c.get('body_part', '')}",
                    f"公开描述：{c.get('description_public', '')}",
                    f"教学用途：{c.get('teaching_note', '')}",
                    "",
                    f"许可：{c['license']}；作者：{c['artist']}",
                    f"来源页：{c['source_page']}",
                    f"本地文件：images/{Path(c['image']).name}",
                    "",
                    "边界：公开教学影像，非本次演示病例；标签来自来源页描述，未经放射科医师逐例复核。",
                ])
                records.append({
                    "title": f"影像｜{r['name']}｜{g['name']}｜{c['title']}",
                    "content": content,
                    "metadata": {
                        "type": "case", "id": c["id"], "modality": c.get("modality", []),
                        "body_part": c.get("body_part", ""), "image": f"images/{Path(c['image']).name}",
                        "license": c["license"], "artist": c["artist"],
                        "region_id": r["id"], "region_name": r["name"],
                        "group_id": g["id"], "group_name": g["name"],
                        "source_url": c["source_page"],
                        "sign_tags": c.get("sign_tags", []),
                        "kb_version": VER, "not_for_diagnosis": True,
                    },
                })
                case_md += [f"#### {c['id']} · {c['title']}", "", content, ""]

    sign_by_id = {x["id"]: x for x in signs}
    case_by_id = {x["id"]: x for x in cases}
    link_md = ["# 征象文字 ↔ 影像区域关联（v1）", "",
               "> 每条同时包含文字锚点与图像锚点；框为人工教学标注，不是模型识别或病灶分割。", ""]
    cur = None
    for link in links:
        sign = sign_by_id.get(link["sign_id"], {})
        case = case_by_id.get(link["image_id"], {})
        if link["sign_id"] != cur:
            cur = link["sign_id"]
            link_md += [f"## {sign.get('name', '')}（{sign.get('en', '')}）", ""]
        regions = "；".join(
            f"{r.get('label', '')}（bbox={r.get('bbox')}，{r.get('laterality_rule', '')}）"
            for r in link.get("regions", [])
        )
        content = "\n".join([
            f"文字锚点：{link.get('quote', '')}",
            f"图像：{case.get('title', '')}（{link['image_id']}）",
            f"标注区域：{regions}",
            f"图注：{link.get('caption', '')}",
            f"对照说明：{link.get('reading', '')}",
            f"标注依据：{link.get('basis', '')}",
            f"标注：{link.get('annotator', '')} · {link.get('annotated_at', '')} · {link.get('review', '')}",
            "",
            f"来源页：{(link.get('evidence') or {}).get('source_page', '')}",
            f"本地文件：images/{Path(case.get('image', '')).name}",
            "",
            "边界：框为人工教学标注，不是模型识别或病灶分割；仅用于文字与影像对照，不构成诊断意见。",
        ])
        records.append({
            "title": f"图文｜{sign.get('name', '')}｜{link['id']}｜{case.get('title', '')}",
            "content": content,
            "metadata": {
                "type": "sign_link", "id": link["id"],
                "sign_id": link["sign_id"], "image_id": link["image_id"],
                "quote": link.get("quote", ""),
                "region_labels": [r.get("label", "") for r in link.get("regions", [])],
                "bboxes": [r.get("bbox") for r in link.get("regions", [])],
                "basis": link.get("basis", ""), "review": link.get("review", ""),
                "source_url": (link.get("evidence") or {}).get("source_page", ""),
                "kb_version": VER, "not_for_diagnosis": True,
            },
        })
        link_md += [f"### {link['id']} · {case.get('title', '')}", "", content, ""]

    with (OUT / "kb-import.jsonl").open("w", encoding="utf8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (OUT / "kb-signs.md").write_text("\n".join(sign_md), encoding="utf8")
    (OUT / "kb-standards.md").write_text("\n".join(std_md), encoding="utf8")
    (OUT / "kb-guidelines.md").write_text("\n".join(gl_md), encoding="utf8")
    readme = (README_TEXT
              .replace("{{SIGNS}}", str(len(signs)))
              .replace("{{STD}}", str(len(standards)))
              .replace("{{GL}}", str(len(guidelines)))
              .replace("{{CASES}}", str(len(cases)))
              .replace("{{LINKS}}", str(len(links)))
              .replace("{{GROUPS}}", str(len(groups)))
              .replace("{{REGIONS}}", str(len(tax.get("regions", []))))
              .replace("{{CONDS}}", str(len(groups)))
              .replace("{{CONDS_IMG}}", str(len([g for g in groups if any(c.get('group_id') == g['id'] for c in cases)])))
              .replace("{{TOTAL}}", str(len(records))))
    (OUT / "README.md").write_text(readme, encoding="utf8")
    (OUT / "kb-cases.md").write_text("\n".join(case_md), encoding="utf8")
    (OUT / "kb-sign-links.md").write_text("\n".join(link_md), encoding="utf8")
    print("exported", len(records), "records ->", OUT)
    print("images:", len(list((OUT / "images").iterdir())))
    print("sign_links:", len(links))


if __name__ == "__main__":
    main()
