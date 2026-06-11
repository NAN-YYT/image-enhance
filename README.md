# image-enhance

> Claude Code Skill — 图片预处理增强管道，补偿 AI 视觉模型在小字、密集 UI、多页合图场景下的识别弱点。

## 解决什么问题

Claude 等视觉模型在以下场景表现不佳：

- 小字/密集文字识别不准确
- 复杂 UI 截图中元素定位偏移
- 多页设计稿合并为一张图时细节丢失
- 手写、低分辨率、高度压缩的图片

本 Skill 通过预处理管道（自动切割 → 放大 → OCR → 领域纠错）在分析前提取结构化信息，显著提高准确率。

## 安装

### 方式一：直接复制到 Claude Code skills 目录

```bash
git clone https://github.com/NAN-YYT/image-enhance.git
cp -r image-enhance ~/.claude/skills/image-enhance
```

### 方式二：符号链接

```bash
git clone https://github.com/NAN-YYT/image-enhance.git ~/path/to/image-enhance
ln -s ~/path/to/image-enhance ~/.claude/skills/image-enhance
```

## 依赖

| 工具 | 用途 | 安装 |
|------|------|------|
| sips | 图片元数据、基础裁剪 | macOS 自带 |
| ImageMagick | 放大、锐化、对比度增强 | `brew install imagemagick` |
| Tesseract | 英文 OCR 备选 | `brew install tesseract tesseract-lang` |
| PyObjC Vision | 中文 OCR（推荐） | `pip3 install pyobjc-framework-Vision pyobjc-framework-Quartz` |

检查依赖是否就绪：

```bash
python3 scripts/enhance_ocr.py --help  # 会自动检测缺失工具
```

## 使用方式

### 在 Claude Code 中

发送图片后输入 `/image-enhance`，Claude 会自动执行预处理管道。

### 命令行手动运行

```bash
# 完整管道：布局检测 → 切割 → 3x放大 → OCR
python3 scripts/enhance_ocr.py "/path/to/image.png"

# 领域词典纠错
python3 scripts/context_correct.py /tmp/image_enhance_pipeline/results.json
```

## 工作原理

```
输入图片
   │
   ├── 1. 检测尺寸和布局（1x1 / 2x1 / 2x2）
   │
   ├── 2. 按网格切割为独立区域
   │
   ├── 3. 每个区域 3x 放大 + 锐化 + 对比度增强
   │
   ├── 4. macOS Vision OCR（中英文混合）
   │
   ├── 5. 按 Y 坐标合并为逻辑行
   │
   └── 6. 领域词典纠错 → 输出结构化 JSON
```

## 领域词典自定义

编辑 `scripts/context_correct.py` 中的 `CORRECTIONS` 字典：

```python
CORRECTIONS = {
    "OCR误识别": "正确文字",
    "效据": "数据",
    "监溯": "监测",
    # 添加你的领域术语...
}
```

内置词典已包含农产品市场监测系统的常见术语（约 120 条映射）。

## 效果对比

以 1448x1086 四页合并设计稿为例：

| 指标 | 无预处理 | 有预处理 + 纠错 |
|------|---------|----------------|
| 标题识别 | 准确 | 准确 |
| 关键术语 | ~40% 正确 | ~90% 正确 |
| 数值数据 | ~60% 正确 | ~85% 正确 |
| 小字描述 | 基本不可读 | 部分可读 |

## 局限性

- AI 生成的设计稿（文字是像素渲染非矢量）效果弱于真实 UI 截图
- 极小字体（<6px 像素高度）即使放大后仍可能无法识别
- 领域纠错依赖预设词典，新领域需要手动添加术语
- 仅支持 macOS（依赖 Vision framework 和 sips）

## 文件结构

```
image-enhance/
├── SKILL.md                    # Claude Code Skill 定义
├── README.md                   # 本文件
└── scripts/
    ├── enhance_ocr.py          # 主管道脚本
    └── context_correct.py      # 领域纠错脚本
```

## License

MIT
