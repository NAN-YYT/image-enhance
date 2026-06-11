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

# 智能纠错（形近字 + 词表验证，推荐）
python3 scripts/smart_correct.py correct /tmp/image_enhance_pipeline/results.json

# 或 Trie 精确匹配纠错
python3 scripts/trie_correct.py correct /tmp/image_enhance_pipeline/results.json
```

### 学习新词

```bash
# 添加一条纠错映射（同时更新 Trie 和 smart_correct）
python3 scripts/smart_correct.py learn "OCR错误" "正确文字"

# 查看某个字的形近字
python3 scripts/smart_correct.py similar "据"

# 测试纠错效果
python3 scripts/smart_correct.py test "包含OCR错误的文本"

# 查看词典统计
python3 scripts/trie_correct.py stats
```

每次学习会自动更新 `scripts/correction_dict.json`，下次使用时生效。

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
   ├── 6. Trie 精确匹配（已知的 错→正 映射）
   │
   └── 7. 形近字相似度 + 词表上下文验证（处理未知错误）
```

## 纠错引擎

### 双层架构

| 层级 | 引擎 | 原理 | 适用场景 |
|------|------|------|----------|
| 第 1 层 | Trie 精确匹配 | 已知 OCR 错误模式 → 正确文字，O(m) 查找 | 见过的错误，秒级修复 |
| 第 2 层 | 形近字 + 词表验证 | 四角码/笔画/部首相似度 → 候选字 → 必须组成已知词才替换 | 未见过的错误，智能修复 |

### 形近字相似度数据

来源：[yongzhuo/char-similar](https://github.com/yongzhuo/char-similar)（MIT），包含：

- `char_fourangle.json` — 四角码编码（形状特征），21K+ 字
- `char_stroke.json` — 笔画分解，21K+ 字
- `char_component.json` — 部首/偏旁，20K+ 字
- `char_struct.json` — 结构类型（左右、上下、包围等），20K+ 字

相似度计算：四角码匹配 40% + 部首相同 25% + 结构相同 15% + 笔画交集 20%

### Trie 字典树

- **贪心最长匹配**：从左到右扫描文本，优先匹配最长的错误模式
- **增量学习**：每次 `learn` 自动持久化到 JSON，支持频率统计
- **短词优化**：大部分纠错词条 2-4 个字，Trie 前缀共享节省内存
- **初始词典**：182 条 OCR 纠错映射，可通过 `learn` 命令持续扩充

### 混淆集（Confusion Set）

来源：[SIGHAN Chinese Spelling Check](https://github.com/sunnyqiny/Confusionset-guided-Pointer-Networks-for-Chinese-Spelling-Check)（学术标准数据集），包含：

- **4,922 个常用汉字**的混淆关系
- **38,469 对**形近字/音近字映射
- 双向索引：正字→易错字 + 错字→正字候选

这是中文拼写纠错领域的标准混淆集，源自 SIGHAN Bake-off 评测任务。相比手动维护 182 条映射，混淆集覆盖了绝大多数中文 OCR 可能出现的字形/字音混淆。

### 上下文词表

`scripts/data/common_words.json` 包含 128 个高频中文词汇，覆盖：
- 通用 UI 术语（数据、系统、管理、监测、分析……）
- 操作动词（删除、编辑、保存、取消……）
- 数据指标（均价、环比、趋势、预警……）
- 技术术语（数据库、接口、采集、爬虫……）

形近字纠错**必须**让候选字与左右邻字组成词表中的已知词，才会替换。这避免了纯字形相似导致的越改越错。

### 自定义扩展

```bash
# 添加纠错映射（自动更新 Trie）
python3 scripts/smart_correct.py learn "新的错误" "正确文字"

# 扩展上下文词表 — 直接编辑 JSON 数组
# scripts/data/common_words.json
```

词表越丰富，形近字纠错覆盖面越广。建议按你的业务领域添加专用词汇。

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
- 形近字纠错依赖上下文词表覆盖度，词表外的词无法触发纠错
- 仅支持 macOS（依赖 Vision framework 和 sips）

## 文件结构

```
image-enhance/
├── SKILL.md                        # Claude Code Skill 定义
├── README.md                       # 本文件
├── LICENSE                         # MIT
└── scripts/
    ├── enhance_ocr.py              # 主管道：切割 + 放大 + OCR
    ├── smart_correct.py            # 智能纠错（混淆集 + 形近字 + 词表验证）
    ├── trie_correct.py             # Trie 精确匹配纠错
    ├── context_correct.py          # 旧版纠错（兼容保留）
    ├── correction_dict.json        # 持久化纠错词典（182条，自动学习更新）
    └── data/
        ├── confusion_set.txt       # SIGHAN 混淆集原始数据 (4922 chars)
        ├── confusion_index.json    # 双向混淆索引 (38469 pairs)
        ├── char_fourangle.json     # 四角码字典 (21K+ chars)
        ├── char_stroke.json        # 笔画分解字典 (21K+ chars)
        ├── char_component.json     # 部首字典 (20K+ chars)
        ├── char_struct.json        # 结构字典 (20K+ chars)
        └── common_words.json       # 上下文验证词表 (128 words, 可扩展)
```

## License

MIT
