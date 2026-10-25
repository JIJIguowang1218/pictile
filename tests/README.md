# 测试资产规范

> **清单、结果、评论、索引走普通 Git，远程同步。**
> **图片不进入 Git**：本地保存在 `tests/images/`（已被 `.gitignore` 忽略），用 U 盘拷贝；换机器时用同步的清单 + sha256 重新定位。
> 本目录会包含仅用于内部测试的网图，**仓库建议保持私有**。

---

## 1. 为什么这样组织

- **图片不进 Git**：避免仓库膨胀、LFS 配额，也避免把许可不明的网图推到远端。
- **索引同步**：清单里有相对路径和 sha256；图片文件夹按同样结构拷贝，换机器就能对上。
- **每张图一个结果 JSON**：评论和指标跟着图片走，避免所有人挤在一个大文件里产生冲突。
- **每批次一份人读总结**：只写结论、分歧和决策，不重复每张图的细节。
- **自动生成索引**：跨批次检索用，不手工编辑。

---

## 2. 目录

```
tests/
├── README.md                       # 本文件
├── images/                         # 图片：本地保存，不进 Git（.gitignore）
│   └── T01-baseline/
│       └── B20261027A/
│           └── T01-B20261027A-I0001.jpg
├── archive/                        # 审核后原图归档：本地，不进 Git
├── manifests/                      # 每批次一份图片清单（同步）
│   └── T01-baseline/
│       └── B20261027A.json
├── results/                        # 每张图一份结果（同步，含多次 run 与评论）
│   └── T01-baseline/
│       └── B20261027A/
│           └── T01-B20261027A-I0001.json
├── reviews/                        # 每批次一份人读总结（同步）
│   └── T01-baseline/
│       └── B20261027A.md
├── schemas/                        # 固定结构定义（同步）
│   ├── manifest.schema.json
│   └── result.schema.json
├── local.example.json              # 本地根目录示例（同步）
├── local.json                      # 本机实际根目录（不同步，.gitignore）
├── tools/                          # 入库、校验、定位、索引
│   ├── common.py
│   ├── add_image.py
│   ├── validate.py
│   ├── locate_images.py
│   └── build_index.py
├── index.csv                       # 自动生成，勿手改（同步）
└── index.md                        # 自动生成，勿手改（同步）
```

---

## 3. 命名

统一格式：

```
{stage}-{batch}-{code}.{ext}
```

示例：`T01-B20261027A-I0001.jpg`

| 片段 | 规则 | 示例 |
| --- | --- | --- |
| stage | `T` + 两位数字 | `T01` |
| batch | `B` + `YYYYMMDD` + 一个大写字母 | `B20261027A` |
| code | `I` + 四位数字，批次内自增 | `I0001` |
| ext | `jpg` / `jpeg` / `png` / `webp` | `.jpg` |

**唯一键**是 `stage + batch + code`。从图片路径可以反推唯一键，从唯一键可以拼出路径，不需要查数据库。

### 阶段码

| 码 | 阶段 | 用途 |
| --- | --- | --- |
| T00 | smoke | 冒烟：跑通、不崩溃 |
| T01 | baseline | 基线出图质量（29×29、12 色、MARD 221） |
| T02 | bg-removal | 背景去除算法对比 |
| T03 | downsample | 降采样算法对比 |
| T04 | palette | 色板子集与色差 |
| T05 | diagnosis | 检查项与诊断 |
| T06 | semantic | 语义重要性 / 容忍度 |
| T07 | ai-check | VLM 特征核对 / 成对比较 |
| T08 | web-usability | 网页 MVP 可用性 |
| T09 | mobile | 手机端 |

### 批次码

- 默认：`B{今天日期}A`，例如 `B20261026A`。
- 同一天第二批：`B20261026B`；依次类推。
- 一个批次内的图片一起入库、一起测试、一起写结论。

---

## 4. 数据结构

### 4.1 批次清单 `manifests/{stage-dir}/{batch}.json`

```json
{
  "stage": "T01",
  "stage_name": "baseline",
  "batch": "B20261027A",
  "created_at": "2026-10-27T10:00:00+08:00",
  "images": [
    {
      "image_id": "T01-B20261027A-I0001",
      "path": "tests/images/T01-baseline/B20261027A/T01-B20261027A-I0001.jpg",
      "sha256": "…",
      "type": "cartoon",
      "source_kind": "web",
      "source_url": "https://…",
      "license": "unknown",
      "difficulty": 3,
      "notes": "用户找的网图，仅内部测试",
      "added_at": "2026-10-27T10:01:00+08:00"
    }
  ]
}
```

### 4.2 单图结果 `results/{stage-dir}/{batch}/{image_id}.json`

一张图可以有多次 run（不同参数/算法），评论写在每次 run 里：

```json
{
  "image_id": "T01-B20261027A-I0001",
  "path": "tests/images/T01-baseline/B20261027A/T01-B20261027A-I0001.jpg",
  "sha256": "…",
  "runs": [
    {
      "run_id": "R20261027A-01",
      "variant": "29x29_12c_area_mard221",
      "date": "2026-10-27",
      "verdict": "pass",
      "metrics": {
        "c01": 0.72,
        "c02": 0.04,
        "c05_p95": 9.1,
        "colors": 11,
        "beads": 812
      },
      "failures": [],
      "comment": "脸能认出来，背景有点碎",
      "reviewer": "owner",
      "updated_at": "2026-10-27T12:00:00+08:00"
    }
  ]
}
```

`verdict` 只能是 `pass` / `fail` / `review`。`failures` 用固定短语，便于统计，例如：`eye_lost`、`text_unreadable`、`outline_blur`、`island_noise`、`skin_shift`、`banding`、`background_clutter`、`subject_too_small`。

### 4.3 批次总结 `reviews/{stage-dir}/{batch}.md`

只写人读结论，例如：

```markdown
# T01 / B20261027A 基线测试总结

- 样本：60 张（卡通 15 / 人物 12 / 宠物 9 / logo 9 / 场景 6 / 文字 3 / 其他 6）
- 通过：41 / 失败：15 / 待复看：4
- 主要失败：眼睛丢失（6）、文字糊（4）、背景碎（3）、色阶断裂（2）
- 结论：29×29 在卡通和 logo 上可用；真人小脸需要裁紧或加描边。
- 下一步：T02 背景去除，优先修发丝和杂背景。
```

---

## 5. 工作流

### 5.1 入库一张图

```bash
python tests/tools/add_image.py \
  --stage T01 \
  --file "C:/path/to/image.jpg" \
  --type cartoon \
  --source-kind web \
  --source-url "https://..." \
  --license unknown \
  --difficulty 3 \
  --note "用户找的网图，仅内部测试"
```

如果图片放在外部盘，加 `--images-root "E:/pictile-images"`；默认写到本机 `tests/images/`。

工具会：

1. 按批次分配 `I0001` 编号；
2. 统一缩到最长边 1600px（有 alpha 保 PNG，否则 JPEG q90）；
3. 计算 sha256；
4. 写入 `tests/images/...`；
5. 追加 `manifests/...`；
6. 创建空的 `results/...`。

### 5.2 跑测试并记录

- 跑完后编辑对应的 `results/...json`，在 `runs[]` 里追加一条。
- 每张图的评论写在该 run 的 `comment`。
- 批次结束后写 `reviews/...md`，只写结论和决策。

### 5.3 校验与索引

```bash
python tests/tools/validate.py
python tests/tools/build_index.py
```

- `validate.py` 检查命名、路径、sha256、结果结构、孤儿文件；有错误返回非零。
- `build_index.py` 生成 `tests/index.csv` 与 `tests/index.md`。

### 5.4 提交与同步

图片不进 Git，只同步清单/结果/评论/索引：

```bash
git add tests
git commit -m "test(T01): add batch B20261027A"
git push origin main
```

图片文件夹单独拷贝（U 盘）：

- 本机：`tests/images/`
- U 盘：把整个 `tests/images/` 目录拷过去，**保持内部结构不变**
- 另一台机器：把目录拷到任意位置，例如 `E:/pictile-images/`，然后运行下面的定位命令

### 5.5 换电脑 / 换路径

```bash
python tests/tools/locate_images.py --root "E:/pictile-images" --check-hash --write-config
python tests/tools/validate.py
```

- `locate_images.py` 用文件名 + sha256 把同步的清单映射到新的根目录，并写 `tests/local.json`。
- `tests/local.json` 是本机配置，不进 Git；换机器时重新生成。
- 之后 `add_image.py` / `validate.py` 会自动使用这个根目录。
- 如果只改了根目录、没有改文件名，索引里的路径和哈希都能对上；如果文件名被改，哈希检查会报出来。
- 也可以不写配置，直接临时指定：`python tests/tools/validate.py --images-root "E:/pictile-images"`。

### 5.6 审核后归档（不删桌面）

```bash
python scripts/archive_staged.py --stage T01 --batch <批次> --staging "C:/Users/86136/Desktop/pictile_T00_待审核"
```

- 暂存内容整体**移动**到 `tests/archive/{stage}/{batch}/`，桌面只留下那个暂存文件夹。
- 这是移动，不是删除；桌面上的其他内容不受影响。
- `tests/archive/` 与 `tests/images/` 一样本地保存，不进 Git。

---

## 6. 隐私与许可

- 网图只用于**内部测试**；每条记录保留 `source_url` 与 `license`，默认 `unknown`。
- 图片不进 Git；但如果你把整个仓库公开，`tests/images/` 仍可能被误传。**建议仓库保持私有。**
- 公开演示/作品集请另建 `demo` 集，只用自有、CC0、已购买或明确授权的图片。
- 人像需本人同意；不要提交身份证、私聊截图等敏感内容。
- 不提交有版权的角色图到公开仓库；内部测试也建议只保留必要样本。

---

## 7. 现在要准备的测试

### T00 冒烟（20 张）

目标：跑通、不崩溃、输出文件齐全，不判断质量。

跑的是 `baseline_v0`：EXIF 校正 → 中心方形裁剪 → 面积平均降采样（多级预降采样防混叠）→ MARD 221 子集（≤12，贪心 k-medoids）→ CIEDE2000 最近色 → PDF/CSV。**不做背景去除、孤立块清理、抖动、AI。**

| 类型 | 数量 |
| --- | --- |
| 卡通 / 动漫角色 | 3 |
| 人物 / 人像 | 3 |
| 宠物 / 动物 | 2 |
| Logo / 扁平图形 | 3 |
| 产品 / 食物 / 风景 | 2 |
| 文字 / 截图 / 地图 | 2 |
| 硬负例 / 抽象 / 其他 | 3 |
| 简单正例（干净背景 + 大主体） | 2 |

### T01 基线（计划 60 张，实际批次 B20261026B 为 103 张）

目标：29×29、12 色、MARD 221 的人工评分；这是第一次真正的质量判断。

实际：**正例 93**（卡通 15、人物 15、宠物 14、Logo 10、产品 13、风景 15、文字 7、截图 4）+ **硬负例 10**。

评分分两组：**正例 93 张**算平均分（目标 ≥3.5/5）；**硬负例 10 张**不参与平均分，单独看系统是否提前警告、是否优雅失败。样本量不均时同时看大类均衡平均（macro）。

评分可用 `python scripts/review_server.py --stage T01 --batch B20261026B --open` 逐张完成。结果分析见 [`docs/14-T01结果与尺寸适配分析.md`](../docs/14-T01结果与尺寸适配分析.md)。

| 类型 | 数量 |
| --- | --- |
| 卡通 / 动漫角色 | 15 |
| 人物 / 人像 | 12 |
| 宠物 / 动物 | 9 |
| Logo / 扁平图形 | 9 |
| 产品 / 食物 / 风景 | 6 |
| 文字 / 截图 / 地图 | 3 |
| 硬负例 / 抽象 / 其他 | 6 |

### T02 背景去除（30 张，可并行收集，基线跑通后再测）

10 张易例（干净背景、清晰主体）、10 张中等（杂背景、相似色）、10 张难例（发丝/毛发、透明、细结构）。类型以人物、宠物、卡通、产品为主。

---

## 8. 一句话

**图片本地保存、U 盘拷贝；清单同步、一图一记录；结果一图一 JSON，结论一批一总结；审核后移入 archive，换机器用哈希重新定位。**
