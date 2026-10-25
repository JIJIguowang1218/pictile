# 一次性脚本

这些脚本不参与运行时，只用于准备测试资产、跑批次或归档。

| 脚本 | 用途 |
| --- | --- |
| `fetch_mard_palette.py` | 从 beadsheet 提取 MARD 221/291 色表，写入 `src/pictile/data/` |
| `stage_t00.py` | 在桌面暂存区下载/生成 T00 的 20 张图，输出总览、清单、审核表 |
| `scan_staging.py` | 扫描用户拖入的 T01 图片文件夹，生成 `清单.csv`、总览、审核表 |
| `ingest_staged.py` | 读取审核通过的 `清单.csv`，调用 `tests/tools/add_image.py` 正式入库 |
| `archive_staged.py` | 把暂存区内容**移动**到 `tests/archive/`（不删除桌面其他东西） |
| `run_t00.py` | 跑 T00 结构性冒烟，写结果、批次总结与汇总 |
| `run_t01.py` | 跑 T01 基线输出 + 结构检查，生成 103 张的评分表与总览 |
| `aggregate_t01.py` | 读取人工评分，更新 verdict，计算平均分/覆盖率/验收状态 |
| `review_server.py` | 本地审核服务：逐张展示原图/处理后图，保存评分与备注 |
| `review_ui.html` | 通用审核前端（配置驱动，换批次不改前端） |
| `review_configs/T01.json` | T01 验收文本、评分口径、失败标签模板 |
| `make_gridless_overview.py` | 生成去格线的单图预览与批次总览（带分数标签） |
| `make_size_variant_overview.py` | 同图跑另一尺寸（默认 58），生成尺寸总览与 29 vs 58 成对对照 |

## T00 工作流（已完成）

```bash
python scripts/stage_t00.py
# 打开 T00_总览.jpg / 清单.csv 审核
python scripts/ingest_staged.py --staging "C:/Users/86136/Desktop/pictile_T00_待审核"
python scripts/archive_staged.py --stage T00 --batch B20261026A --staging "C:/Users/86136/Desktop/pictile_T00_待审核"
python tests/tools/validate.py
python tests/tools/build_index.py
python scripts/run_t00.py --batch B20261026A
```

## T01 工作流

```bash
# 1) 用户把图片拖进桌面临时文件夹的中文类型子目录
# 2) 扫描并生成清单/总览/审核表
python scripts/scan_staging.py --staging "C:/Users/86136/Desktop/pictile_T00_待审核"

# 3) 审核 清单.csv：通过 / 拒绝 / 替换

# 4) 正式入库
python scripts/ingest_staged.py --stage T01 --staging "C:/Users/86136/Desktop/pictile_T00_待审核"

# 5) 把暂存内容移动进项目归档，桌面清空（不是删除）
python scripts/archive_staged.py --stage T01 --batch <批次号> --staging "C:/Users/86136/Desktop/pictile_T00_待审核"

# 6) 跑 T01 自动部分，生成图纸与评分表
python scripts/run_t01.py --batch <批次号>

# 7) 填 out/T01/<批次号>/rating.csv 的评分/失败标签/评论
python scripts/aggregate_t01.py --batch <批次号>

# 8) 校验与索引
python tests/tools/validate.py
python tests/tools/build_index.py
```

当前批次 B20261026B：103 张（正例 93 + 硬负例 10），自动结构 103/103 通过；质量评分待人工填写。

## 审核前端

```bash
python scripts/review_server.py --stage T01 --batch B20261026B --open
```

打开 `http://127.0.0.1:8765/`。

- 一张图：左原图、右处理后图、3cm 预览、尺寸/色数/豆数/ΔE、颜色表。
- 右侧常驻验收标准；分数 + 备注两个主输入，失败标签可选。
- 点 `确认并下一张` 写入：
  - `out/<stage>/<batch>/review/<image_id>.json`（结构化记录）
  - `out/<stage>/<batch>/rating.csv`（汇总入口）
- 验收文本在 `out/<stage>/<batch>/review_config.json`，首次运行从 `scripts/review_configs/<stage>.json` 复制；换批次只改这个文件，不改前端。
- 全部评完后运行 `python scripts/aggregate_t01.py --batch <批次>`。

## 去格线总览

```bash
python scripts/make_gridless_overview.py --batch B20261026B
```

生成 `out/T01/B20261026B/overview_gridless.jpg` 和每图的 `preview_gridless.png`；不含格子线，标签带分数与类型。

## 尺寸对照

```bash
# 同图同色板，只改网格；默认 58（2×2 板）
python scripts/make_size_variant_overview.py --batch B20261026B --grid 58
```

生成 `out/T01/B20261026B/size_58/overview_58_gridless.jpg`、`paired_29_vs_58.jpg`、`size_58_summary.csv`。不改正式 T01 结果，只做对照。

当前 58×58 批次标记为 `pending_review`（0/103），记录见 `tests/reviews/T01-baseline/B20261026B-size58.md`；本机状态文件为 `out/T01/B20261026B/size_58/status.json`。

规则：**桌面只保留一个暂存文件夹；入库后移动进项目，不删除桌面上的其他内容。** 图片不进 Git，正式副本在 `tests/images/`，原图归档在 `tests/archive/`（均本地）。
