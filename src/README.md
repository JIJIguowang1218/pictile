# 源码目录（规划）

正式算法代码放 `src/pictile/`，与测试工具、一次性脚本分开：

```
src/pictile/
├── palette.py      # 色板加载、sRGB→Lab、CIEDE2000、子集选择
├── imaging.py      # 裁剪、降采样、主导色、连通域清理
├── pipeline.py     # baseline_v0 固定 DAG
├── render.py       # 网格预览、PDF、CSV
└── diagnose.py     # 08 的检查项与 simulate
```

## 约束

- 纯函数：不读文件、不读时间、不随机；输入输出可 JSON 序列化。
- 色板版本、参数、区域 ID 显式传入；不在函数里藏全局状态。
- `tests/tools/` 只放测试资产管理工具；`scripts/` 只放一次性脚本。
- 依赖统一从仓库根目录的 `requirements.txt` / `requirements-dev.txt` 安装。
