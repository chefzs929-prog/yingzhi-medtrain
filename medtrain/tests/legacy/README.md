# legacy 验收脚本（已失效，仅存档）

这里的脚本对应**已经下线的产品形态**，不再纳入复现清单，跑不通是预期行为。

| 脚本 | 对应形态 | 失效原因 |
| --- | --- | --- |
| `ui_check.py` | 「多版本软件」逐版验收（v1–v7 多角色 SPA） | 依赖 `outputs/medtrain` 下已删除的旧版页面与 8800 端口；现版本已收缩为「一个首页 + 阅片 + 病例题 + 对比 + 课堂 + 学生实验室」 |
| `body3d_check.py` | 首页人体 3D 模型 | 3D 首页与 `body-3d.js` / `models/` 已在 v7 收缩中下线，8790 端口不再存在 |

## 现在的验收入口

```
python3 medtrain/build.py
cd outputs/medtrain && python3 -m http.server 8811
python3 medtrain/tests/site_check.py        # 全站入口
python3 medtrain/tests/chest_check.py       # 阅片工作台
python3 medtrain/tests/exam_check.py        # 病例题 + 对比阅片
python3 medtrain/tests/classroom_check.py   # 课堂
python3 medtrain/tests/student_lab_check.py # 学生实验室
python3 medtrain/tests/qa_eval.py           # 问答 30 条
python3 medtrain/tests/refusal_eval.py      # 拒答 / 命中 50 条
python3 kb/scripts/crosscheck.py            # JS / Python 交叉验证
python3 -m unittest discover -s kb/tests    # 知识库单元测试
```

## 为什么不直接删掉

它们记录了曾经做过的验收口径，答辩被问到"以前那版怎么验的"时可以指出来。但**不能**再被 README 当作可复现步骤引用——脚本存在却跑不通，比没有更伤可信度。
