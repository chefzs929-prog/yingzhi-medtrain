"""影像入口：认图 + 取框。

两件事，都只做确定性判断，不做猜测：

1. match_image：上传的图属于库内哪一例。只用 md5 精确比对。
   纯标准库没有 JPEG 解码器，算不了感知哈希，所以截图、压缩转发过的图
   会匹配失败——这时如实返回 None，由上层走「未落到已标注分区就不下结论」，
   而不是挑一张最像的顶上去。

2. extract_bbox：模型按约定会在正文末尾附 {"bbox":[x1,y1,x2,y2]}。
   这里把它从正文里剥离（不能把 JSON 甩给用户看），并转成
   locate.js 需要的 [x,y,w,h]。
"""

import base64
import hashlib
import json
import os
import re

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp")

# 模型给的框偶尔不是 0-1，而是 0-1000（Qwen 系的常见约定）。
_SCALE_HINT = 1.5


def _md5(data):
    return hashlib.md5(data).hexdigest()


def data_url_bytes(value):
    """把 data URL 或 bytes 统一成 bytes。"""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if not isinstance(value, str):
        raise ValueError("image must be data-url or bytes")
    s = value.strip()
    if not s.startswith("data:"):
        raise ValueError("not a data url")
    _, _, payload = s.partition(",")
    if ";base64" in s.split(",", 1)[0]:
        return base64.b64decode(payload)
    return payload.encode("utf8")


class ImageIndex:
    """kb/images 的 md5 → case_id 索引。首次查询时构建，之后常驻内存。"""

    def __init__(self, images_dir):
        self.images_dir = images_dir
        self._map = None

    def build(self):
        mapping = {}
        if not os.path.isdir(self.images_dir):
            self._map = mapping
            return mapping
        for name in sorted(os.listdir(self.images_dir)):
            if not name.lower().endswith(IMAGE_EXT):
                continue
            stem = os.path.splitext(name)[0]
            # case-001.jpg → CASE-001；命名不合规的直接跳过，不做模糊推断
            m = re.match(r"case-(\d+)$", stem, re.I)
            if not m:
                continue
            path = os.path.join(self.images_dir, name)
            try:
                with open(path, "rb") as fh:
                    digest = _md5(fh.read())
            except OSError:
                continue
            mapping.setdefault(digest, []).append("CASE-%s" % m.group(1))
        self._map = mapping
        return mapping

    @property
    def map(self):
        if self._map is None:
            self.build()
        return self._map

    def match_all(self, image):
        """同一张图可能被多例共用（共享视角），必须把候选都带出来。"""
        try:
            return list(self.map.get(_md5(data_url_bytes(image))) or [])
        except (ValueError, TypeError):
            return []

    def match(self, image):
        found = self.match_all(image)
        return found[0] if found else None

    def __len__(self):
        return len(self.map)


_BBOX_KEY = re.compile(r'"(bbox|box_2d|bbox_2d)"\s*:\s*(\[[^\]]*\]|\{[^{}]*\})', re.I)


def extract_json(text):
    """从模型输出里取第一个 JSON 对象。

    兼容三种常见形态：裸 JSON、```json 围栏、正文里夹一个对象。
    取不到返回 None，不抛异常。
    """
    if not text:
        return None
    s = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", s, re.I)
    if fence:
        s = fence.group(1).strip()
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[start:i + 1])
                except Exception:
                    return None
    return None


def _norm_bbox(raw):
    """把模型给的 4 个数统一成 [x,y,w,h]，0-1。"""
    vals = [float(v) for v in raw]
    if len(vals) != 4:
        return None
    # 千分制（Gemini/Qwen 常见）：全部 > 1.5 且 <= 1000
    if max(vals) > 1.5:
        if max(vals) <= 1000:
            vals = [v / 1000.0 for v in vals]
        else:
            return None
    vals = [max(0.0, min(1.0, v)) for v in vals]
    x, y, a, b = vals
    # 新契约是 [x,y,w,h]；若按宽高算会越界，则按 [x1,y1,x2,y2] 解释。
    if x + a > 1.02 or y + b > 1.02:
        x1, y1, x2, y2 = sorted((x, a))[0], sorted((y, b))[0], sorted((x, a))[1], sorted((y, b))[1]
        w, h = x2 - x1, y2 - y1
    else:
        w, h = a, b
    if w <= 0 or h <= 0:
        return None
    return [round(x, 4), round(y, 4), round(w, 4), round(h, 4)]


def extract_bbox(text):
    """从模型正文里取出 bbox。

    返回 (bbox, raw, stripped)：
        bbox     [x, y, w, h]，0-1 归一化，可直接喂 locate.js；取不到为 None
        raw      模型原始给法
        stripped 去掉这段 JSON 后的正文

    兼容 [x,y,w,h]、[x1,y1,x2,y2]、千分制、{"bbox":{"x":..}}。
    """
    if not text:
        return None, None, text
    m = None
    for m in _BBOX_KEY.finditer(text):
        pass  # 取最后一个：模型常在结尾给框
    if not m:
        return None, None, text

    key = (m.group(1) or "bbox").lower()
    blob = m.group(2).strip()
    try:
        obj = json.loads(blob)
        if isinstance(obj, dict):
            raw = [obj.get("x", 0), obj.get("y", 0), obj.get("w", obj.get("width", 0)),
                   obj.get("h", obj.get("height", 0))]
        else:
            raw = obj
    except (ValueError, TypeError):
        return None, None, text

    if key == "box_2d" and len(raw) == 4:
        # Gemini 约定：[y_min, x_min, y_max, x_max]，0-1000
        y1, x1, y2, x2 = [float(v) for v in raw]
        if max(raw) > 1.5:
            y1, x1, y2, x2 = y1 / 1000.0, x1 / 1000.0, y2 / 1000.0, x2 / 1000.0
        # 已经知道是 x1y1x2y2，先转成 xywh，避免 _norm_bbox 再猜一次
        raw = [x1, y1, max(0.0, x2 - x1), max(0.0, y2 - y1)]

    bbox = _norm_bbox(raw)
    if not bbox:
        return None, None, text
    stripped = (text[:m.start()] + text[m.end():]).rstrip()
    return bbox, raw, stripped
