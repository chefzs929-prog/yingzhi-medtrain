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


_BBOX_JSON = re.compile(r"```(?:json)?\s*(\{[^{}]*\"bbox\"[^{}]*\})\s*```"
                        r"|(\{[^{}]*\"bbox\"[^{}]*\})", re.I)


def extract_bbox(text):
    """从模型正文里取出 bbox。

    返回 (bbox, raw, stripped)：
        bbox     [x, y, w, h]，0-1 归一化，可直接喂 locate.js；取不到为 None
        raw      模型原始给法 [x1, y1, x2, y2]
        stripped 去掉这段 JSON 后的正文
    """
    if not text:
        return None, None, text
    m = None
    for m in _BBOX_JSON.finditer(text):
        pass  # 取最后一个：模型常在结尾给框
    if not m:
        return None, None, text

    blob = m.group(1) or m.group(2)
    try:
        obj = json.loads(blob)
        raw = [float(v) for v in obj["bbox"]]
    except (ValueError, KeyError, TypeError):
        return None, None, text
    if len(raw) != 4:
        return None, None, text

    if max(raw) > _SCALE_HINT:
        raw = [v / 1000.0 for v in raw]

    x1, y1, x2, y2 = raw
    x1, x2 = sorted((max(0.0, min(1.0, x1)), max(0.0, min(1.0, x2))))
    y1, y2 = sorted((max(0.0, min(1.0, y1)), max(0.0, min(1.0, y2))))
    w, h = x2 - x1, y2 - y1
    if w <= 0 or h <= 0:
        return None, None, text

    stripped = (text[:m.start()] + text[m.end():]).rstrip()
    return [round(x1, 4), round(y1, 4), round(w, 4), round(h, 4)], raw, stripped
