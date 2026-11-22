/* 用 JavaScriptCore 跑原型里的纯计算与数据自检 */
/* 运行：jsc tests/test_region_demo.js（在 kb/ 下）或 jsc kb/tests/test_region_demo.js（在项目根） */
var CANDIDATES = ["web/region-cite.template.html", "kb/web/region-cite.template.html"];
var html = null;
for (var i = 0; i < CANDIDATES.length; i++) {
  try { html = read(CANDIDATES[i]); break; } catch (e) {}
}
if (!html) throw new Error("找不到 region-cite.template.html，请在项目根或 kb/ 下运行");

var dbStart = html.indexOf("const DB = {");
var pureStart = html.indexOf("/* PURE-START");
var pureEnd = html.indexOf("/* PURE-END */") + "/* PURE-END */".length;
if (dbStart < 0 || pureStart < 0 || pureEnd < 0) throw new Error("提取失败");

var code = html.slice(dbStart, pureStart) + html.slice(pureStart, pureEnd);

var TEST = String(function(){
  var pass = 0, fail = 0;
  function ok(cond, name, detail){
    if(cond){ pass++; print("  PASS  " + name); }
    else { fail++; print("  FAIL  " + name + "  ::  " + (detail || "")); }
  }
  function locate(key, bbox){
    var d = DB[key];
    var scored = d.regions.map(function(r){ return scoreRegion(bbox, r); })
      .sort(function(a,b){ return b.score - a.score; });
    return judge(scored);
  }

  print("== 定位判定 ==");
  var r;

  r = locate("CASE-006", [0.15,0.40,0.25,0.15]);
  ok(r.status==="single" && r.top.region.id==="REG-006-RML", "右肺中野内部框选 → 单一主分区",
     r.status + " / " + (r.top && r.top.region.id));

  r = locate("CASE-006", [0.12,0.50,0.30,0.12]);
  ok(r.status==="cross", "横跨中野/下野 → 判为跨区不硬猜", r.status);
  ok(r.top && r.second && r.top.region.id!==r.second.region.id, "跨区给出两个不同候选", "");

  r = locate("CASE-006", [0.96,0.02,0.04,0.04]);
  ok(r.status==="uncovered", "图外空白 → 未覆盖", r.status);

  r = locate("CASE-011", [0.35,0.32,0.30,0.28]);
  ok(r.status==="single" && r.top.region.id==="REG-011-CENTER", "超声中央低回声区命中", r.status + " / " + (r.top && r.top.region.id));

  r = locate("CASE-001", [0.20,0.40,0.20,0.12]);
  ok(r.status==="single" && r.top.region.id==="REG-001-RML", "胸片图像左侧中部 → 右肺中野", r.status + " / " + (r.top && r.top.region.id));

  print("== 侧别安全 ==");
  var rml = DB["CASE-001"].regions.filter(function(x){ return x.id==="REG-001-RML"; })[0];
  ok(rml.imageSide==="left" && rml.patientSide==="right", "图像左侧 = 患者右侧（PA 位）",
     rml.imageSide + "/" + rml.patientSide);
  var allLaterality = true;
  Object.keys(DB).forEach(function(k){
    DB[k].regions.forEach(function(x){
      if(x.imageSide==="left" && x.patientSide!=="right") allLaterality = false;
      if(x.imageSide==="right" && x.patientSide!=="left") allLaterality = false;
      if(x.imageSide==="midline" && x.patientSide!=="midline") allLaterality = false;
      if(x.imageSide==="unknown" && x.patientSide!=="unknown") allLaterality = false;
    });
  });
  ok(allLaterality, "全部分区的左右映射一致", "");

  print("== 引用门禁 ==");
  var claims = [];
  Object.keys(DB).forEach(function(k){ DB[k].claims.forEach(function(c){ claims.push({img:k, c:c}); }); });
  ok(claims.length >= 6, "演示集 claim 数量 " + claims.length, "");

  var dualOK = true, singleOK = true, brokenOK = true, regionOK = true;
  claims.forEach(function(o){
    var c = o.c;
    if(c.status==="dual" && !(c.spatial && c.doc && c.spatial.hash && c.doc.hash)) dualOK = false;
    if(c.status==="single" && !(c.spatial===null && c.gateReason)) singleOK = false;
    if(c.status==="broken" && !(c.gate && c.gate.expected && c.gate.actual && c.gate.expected!==c.gate.actual)) brokenOK = false;
    var regs = DB[o.img].regions.map(function(x){ return x.id; });
    if(regs.indexOf(c.regionId) < 0) regionOK = false;
  });
  ok(dualOK, "dual 条目两侧锚点与 hash 齐全", "");
  ok(singleOK, "single 条目显式标注缺失原因", "");
  ok(brokenOK, "broken 条目有 expected/actual 差异（可拦截）", "");
  ok(regionOK, "所有 claim 指向存在的分区", "");

  var st = {dual:0, single:0, broken:0};
  claims.forEach(function(o){ st[o.c.status]++; });
  ok(st.dual===5 && st.single===1 && st.broken===1, "门禁统计 dual5 / single1 / broken1",
     JSON.stringify(st));

  print("== 数据完整性 ==");
  var geomOK = true, signOK = true;
  Object.keys(DB).forEach(function(k){
    DB[k].regions.forEach(function(x){
      var b = x.coords;
      if(b[0]<0 || b[1]<0 || b[0]+b[2]>1.0001 || b[1]+b[3]>1.0001 || b[2]<=0 || b[3]<=0) geomOK = false;
      if(!x.signs || !x.signs.length) signOK = false;
    });
  });
  ok(geomOK, "分区坐标全部落在 [0,1] 内且非退化", "");
  ok(signOK, "每个分区至少绑定 1 个可对照征象", "");

  var atlasOK = true;
  Object.keys(DB).forEach(function(k){
    var a = DB[k].atlas;
    if(!(a.id && a.level && a.annotator && a.annotatedAt)) atlasOK = false;
    if(DB[k].atlas.level==="local" && DB[k].regions.some(function(x){ return x.patientSide!=="unknown"; })) atlasOK = false;
  });
  ok(atlasOK, "atlas 元数据齐全；local 级不推断侧别", "");

  print("");
  print("RESULT  pass=" + pass + "  fail=" + fail);
  if(fail) throw new Error("有 " + fail + " 项失败");
});

eval("var IMGS = {};\n" + code + "\n(" + TEST + ")();");
