/* 静态模式：把 serve_region.py 的框选定位算法移植到浏览器，避免依赖后端。
 * 算法与 kb/scripts/serve_region.py#locate 保持一致：
 *   score = 0.7 * coverage + 0.3 * purity
 *   coverage = 选区落在该分区的面积 / 选区面积
 *   purity   = 选区落在该分区的面积 / 该分区面积
 */
(function () {
  const T = {
    cross_gap: 0.15,
    min_coverage: 0.35,
    second_min: 0.25,
    min_side: 0.015,
    max_area: 0.60,
  };
  const SIDE_LABEL = { right: "患者右侧", left: "患者左侧", midline: "中线", unknown: "侧别未知" };

  const area = (b) => Math.max(0, b[2]) * Math.max(0, b[3]);
  function inter(a, b) {
    const x1 = Math.max(a[0], b[0]);
    const y1 = Math.max(a[1], b[1]);
    const x2 = Math.min(a[0] + a[2], b[0] + b[2]);
    const y2 = Math.min(a[1] + a[3], b[1] + b[3]);
    return Math.max(0, x2 - x1) * Math.max(0, y2 - y1);
  }

  function card(s) {
    const r = s.region;
    return {
      region: r,
      coverage: Math.round(s.coverage * 1e4) / 1e4,
      purity: Math.round(s.purity * 1e4) / 1e4,
      score: Math.round(s.score * 1e4) / 1e4,
      side_label: SIDE_LABEL[r.patient_side] || r.patient_side,
    };
  }

  function locate(regions, bbox) {
    const b = [
      Math.max(0, Math.min(1, Number(bbox[0]))),
      Math.max(0, Math.min(1, Number(bbox[1]))),
      Math.max(0, Math.min(1, Number(bbox[2]))),
      Math.max(0, Math.min(1, Number(bbox[3]))),
    ];
    b[2] = Math.max(0, Math.min(1 - b[0], b[2]));
    b[3] = Math.max(0, Math.min(1 - b[1], b[3]));

    const list = (regions || []).filter((r) => r && r.coords && r.coords.length === 4);
    if (!list.length) {
      return { status: "no_atlas", message: "该影像未标注分区，无法区域定位", bbox: b };
    }

    const scored = list.map((r) => {
      // 站点数据 data/chest/*.json 的 zone.coords 是 [left, top, w, h]，
      // 与知识库 regions.jsonl 的 [x1,y1,x2,y2] 不同，这里不要再转换。
      const a = inter(b, r.coords);
      const coverage = a / Math.max(1e-9, area(b));
      const purity = a / Math.max(1e-9, area(r.coords));
      return { region: r, overlap: a, coverage, purity, score: 0.7 * coverage + 0.3 * purity };
    }).sort((x, y) => y.score - x.score);

    const top = scored[0];
    const second = scored[1] || null;

    if (b[2] < T.min_side || b[3] < T.min_side) {
      return { status: "too_small", message: "选区过小，请扩大后再定位", bbox: b };
    }

    // 大范围病变（气胸 / 大量积液）：用 purity 判断"哪些分区被覆盖"，
    // 不用 coverage——后者随框变大趋近 0，等于惩罚大框。
    const strong = scored.filter((x) => x.purity >= 0.75);
    if (area(b) > T.max_area || strong.length >= 2) {
      const base = strong.length ? strong : scored.filter((x) => x.coverage >= 0.2);
      const hit = base.slice().sort((x, y) => y.purity - x.purity);
      if (hit.length) {
        return {
          status: "diffuse",
          message: "选区覆盖范围较大，按「分区被覆盖比例」列出可能累及的分区；这是范围推断，不宜据此判断单一分区",
          bbox: b,
          regions: hit.slice(0, 5),
        };
      }
    }

    if (top.coverage < T.min_coverage && top.purity < 0.8) {
      return { status: "uncovered", message: "该图未标注此区域，本工具不对未标注区域作推断", bbox: b };
    }
    if (second && top.score - second.score < T.cross_gap && second.coverage > T.second_min) {
      return {
        status: "cross",
        message: "选区同时落在两个分区，请缩小范围或直接点选分区",
        bbox: b,
        candidates: [card(top), card(second)],
        gap: top.score - second.score,
      };
    }
    return {
      status: "single",
      bbox: b,
      primary: card(top),
      secondary: second && second.coverage > 0.12 ? card(second) : null,
      mode: "box",
    };
  }

  window.YZLocate = { locate, thresholds: T };
})();
