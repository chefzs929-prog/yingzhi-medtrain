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
    if (area(b) > T.max_area) {
      return { status: "too_large", message: "选区过大，请缩小到单一分区后再定位", bbox: b };
    }
    if (b[2] < T.min_side || b[3] < T.min_side) {
      return { status: "too_small", message: "选区过小，请扩大后再定位", bbox: b };
    }

    const scored = list.map((r) => {
      const a = inter(b, r.coords);
      const coverage = a / Math.max(1e-9, area(b));
      const purity = a / Math.max(1e-9, area(r.coords));
      return { region: r, overlap: a, coverage, purity, score: 0.7 * coverage + 0.3 * purity };
    }).sort((x, y) => y.score - x.score);

    const top = scored[0];
    const second = scored[1] || null;

    if (top.coverage < T.min_coverage) {
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
