# IRI Analyzer 使用指南

IRI Analyzer 是一个本地运行的蔗糖法 IRI 显微图像冰晶面积分析工具。它提供网页界面，适合不写代码地批量导入图片、调整关键参数、查看完整中间图、导出 CSV/JSON/PNG/ZIP 结果。

本项目的核心原则：

- Hough/LoG 只用于寻找候选冰晶位置，不作为面积测量。
- 最终面积来自每个冰晶的实际实例 mask，即 `actual_area_px2`。
- 默认科学汇总优先使用 `accepted_total_actual_area_px2`。
- 没有填写像素尺寸时，只输出 `px²`；填写 `um/px` 后才输出 `um²`。
- 自动结果是图像分割估计，不应直接当作最终科学结论。每批数据都建议检查 `10_final_overlay.png` 和 `11_label_overlay.png`。

## 第一次使用：无需手敲命令

在 Windows 上，普通使用者只需要双击根目录下的两个脚本。

### 第一步：双击安装环境

双击：

```text
01_setup_environment.cmd
```

这个脚本会自动检查并准备项目运行环境：

- 检查 Python 环境；如果没有，会优先尝试用 Windows `winget` 自动安装 Python。
- 检查 Node.js/npm；如果没有，会优先尝试用 `winget` 自动安装 Node.js LTS。
- 创建本项目专用 Python 虚拟环境 `.venv`。
- 安装 Python 图像分析依赖。
- 安装前端依赖。
- 构建本地网页前端。
- 运行一次快速测试，确认项目可用。

如果你的系统没有 `winget`，脚本会自动打开 Python 或 Node.js 的官方下载页面。安装完成后，再次双击 `01_setup_environment.cmd` 即可继续。

安装成功后，窗口会显示 `Setup complete`。

Linux 用户可在终端中运行：

```bash
sh 01_setup_environment.sh
```

该脚本会尝试通过系统包管理器安装 Python 3.10+、Node.js 18+、npm 和必要依赖，然后构建前端并运行测试。

### 第二步：双击启动网页

双击：

```text
02_start_web_ui.cmd
```

这个脚本会：

- 检查本地环境是否已经安装好。
- 启动 IRI Analyzer 本地网页服务。
- 自动在默认浏览器打开：

```text
http://127.0.0.1:8000
```

使用网页时，请保持启动脚本打开的黑色窗口不要关闭。关闭窗口或按 `Ctrl+C` 会停止服务。

## 网页怎么用

### 1. 选择图片

进入网页后，在“分析”页点击“选择图片”，可以一次选择一张或多张显微图。

支持格式：

```text
bmp, png, jpg, jpeg, tif, tiff
```

也可以把图片拖拽到上传区域。

### 2. 选择预设

右侧有三个预设：

- `默认`：通用参数，适合先试跑。
- `0.1 PVA`：偏向圆形、分离冰晶。
- `0.2 PVA`：增强方形/短棒状冰晶识别，并允许保守的轻微粘连分裂。

如果先选了某个预设，又手动调整了下面的参数，最终运行会使用：

```text
所选预设作为基础 + 手动调整参数覆盖同名项
```

此时预设按钮会取消高亮，避免误以为仍是完全原始预设。

### 3. 常用参数

- `像素尺寸 um/px`：显微标定值。例如每像素 `0.5 um`，就填写 `0.5`。不确定时留空，不要填写单位。
- `排除贴边对象`：开启后，贴到图像边缘的对象不进入 accepted 科学统计。
- `方形策略`：自动、开启、关闭。用于补充识别方形、矩形、多边形冰晶。
- `粘连分裂`：自动、开启、关闭。用于保守处理轻微粘连对象。

高级参数可以展开，用于调整背景、候选、轮廓、面积过滤、方形识别和粘连分裂阈值。参数调整会保留在当前页面状态中，切换到历史或结果页再回来不会丢失；刷新浏览器页面才会恢复默认。

### 4. 开始分析

点击“开始分析”。批量图片会依次处理，避免同时占满 CPU。

处理完成后可以点击“查看结果”。

### 5. 查看结果

结果页会展示每张图片的：

- 原图和灰度图
- 背景估计与背景校正图
- 候选定位图
- accepted/rejected 候选图
- 方形候选和方形轮廓图
- 径向可靠点和轮廓恢复图
- 粘连 parent 和 split 图
- 实例 mask
- final overlay
- label overlay
- 面积直方图
- QC 报告

历史页会按处理时间倒序显示已分析过的图片缩略图、图片名和处理时间。

## 可以导出什么

网页支持：

- 下载单张中间图。
- 下载单张图片的完整结果 ZIP。
- 下载整批分析的完整 ZIP。
- 下载 `crystals.csv`、`candidates_accepted.csv`、`candidates_rejected.csv`、`summary.json`、`qc_report.txt`。

所有网页运行结果默认保存在：

```text
results/web_runs/
```

每张图会有独立输出文件夹。

## 本项目能做什么

IRI Analyzer 可以：

- 对单张或批量 IRI 显微图进行分析。
- 做不规则背景阴影校正。
- 输出完整中间处理图片，便于人工检查。
- 识别圆形或近圆形冰晶。
- 在门控触发时补充识别方形、矩形、多边形冰晶。
- 对轻微粘连对象做保守分裂。
- 输出每个冰晶的实际 mask 面积。
- 输出 accepted/raw 两套统计，避免 QC warning 对象直接混入主统计。
- 生成 QC 报告，标记贴边、重叠、异常面积、弱边界等可疑对象。

## 方法说明

默认处理顺序为：

```text
gray -> candidate protect mask -> background estimate from raw gray -> flat-field correction -> CLAHE -> candidate detection -> contour/mask refinement -> measurement -> QC
```

默认不建议“先 CLAHE 再估背景”，因为 CLAHE 会增强阴影、噪声和冰晶边缘，使背景估计带入伪结构。

圆形候选使用 Hough/LoG 定位，但面积不来自圆面积。圆形对象会通过可靠径向射线恢复实际轮廓。

方形或多边形候选走 contour-mask refinement，不强行拟合成正方形或矩形。面积仍来自最终实例 mask 的像素数。

粘连分裂只处理高置信的轻微粘连。严重团聚、严重模糊、边界缺失对象默认需要人工 QC，必要时应考虑 Cellpose 等学习型分割方法。

## 重点检查哪些结果

每批数据至少抽查：

- `03_background_estimate.png`：应主要是大尺度阴影，不应明显包含冰晶边缘。
- `04_flatfield_corrected.png`：背景应比原图更均匀。
- `06b_candidate_accepted_overlay.png`：accepted 候选应覆盖主要冰晶。
- `06c_candidate_rejected_overlay.png`：rejected 对象应主要是弱边界、噪声、贴边或可疑结构。
- `07d_square_contour_refined_overlay.png`：方形冰晶轮廓应贴近真实边界。
- `07g_cluster_split_overlay.png`：粘连拆分不应把纹理碎片误当冰晶。
- `10_final_overlay.png`：最终轮廓应贴近实际外轮廓。
- `11_label_overlay.png`：编号应能与 `crystals.csv` 对应。
- `qc_report.txt`：需要人工判断 warning 对象是否保留。

## 常见问题

### 双击安装脚本后提示没有 Python 或 Node.js

脚本会优先尝试用 `winget` 自动安装。如果无法自动安装，会打开官方下载页面。安装完成后，再次双击 `01_setup_environment.cmd`。

### 双击启动后网页打不开

确认：

- 是否已经运行过 `01_setup_environment.cmd`。
- 启动窗口是否仍然打开。
- 浏览器访问的是 `http://127.0.0.1:8000`。
- 如果 8000 端口被占用，先关闭旧的 IRI Analyzer 启动窗口，再重新双击启动脚本。

### 点击“选择图片”没有反应

请刷新网页后再试。当前版本使用显式按钮触发系统文件选择器，并支持拖拽图片到上传区域。

### 面积单位为什么只有 px²

因为没有填写 `像素尺寸 um/px`。例如显微标定为每像素 `0.5 um`，就在参数中填写 `0.5`。

### 为什么最终面积不是圆面积

圆形检测只用于定位。最终面积来自每个实例 mask 的像素面积，`circle_area_px2` 只作为参考字段。

## 命令行用法（可选）

普通用户不需要命令行。需要批处理或调试时，可以使用：

```bash
python -m iri_analyzer.cli --input path/to/image.bmp --output output_dir --mode qc
python -m iri_analyzer.cli --input image_folder --output output_dir --mode batch
python -m iri_analyzer.cli --input image.bmp --output output_dir --mode sensitivity
```

也可以手动启动网页：

```bash
python -m iri_analyzer.web
```

推荐普通使用者优先使用两个双击脚本。
