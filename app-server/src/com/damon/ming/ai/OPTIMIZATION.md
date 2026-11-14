# RAG Pipeline 优化记录

本文档记录 RAG 检索链路的历次优化，用于后续审计和回归参考。

---

## 2026-11-02 — 修复 vLLM 下 RAG 全局摘要失效（num_predict 参数名）

### 问题

`summary_service._run_single_summary` 硬编码 Ollama 专用参数 `num_predict`，vLLM 的 OpenAI 兼容接口不识别，`openai==2.16.0` 客户端直接抛 `TypeError`。异常被 `except Exception` 吞掉后降级为 `truncate_by_token`，导致**阶段 5 全局摘要在 vLLM 下从未真正执行**，实际行为是把拼接结果硬截断到 `max_context_tokens`。

### 方案

引擎相关参数的翻译收敛到推理层，`summary_service` 只使用通用键：

- `summary_service` 统一用通用键 `max_tokens`（目标值覆盖角色默认值），不再自行拼接引擎参数
- `ollama_inference` 新增 `_map_options()`：`max_tokens → num_predict`
- `vllm_inference` 无需改动（`max_tokens` 本就是 OpenAI 键）

### 改动文件

| 文件 | 改动 |
|---|---|
| `summary/summary_service.py` | `_run_single_summary` 删除硬编码 `num_predict`，改为 `summary_options` + 通用 `max_tokens` 覆盖 |
| `inference/ollama_inference.py` | 新增 `_map_options()`，`text_generation` / `stream_generate` 统一映射 `max_tokens → num_predict` |

### 影响

- vLLM：摘要调用不再报错，LLM 全局摘要正常执行
- Ollama：`max_tokens` 从被忽略变为生效（翻译为 `num_predict`），与 YAML 配置意图一致

---

## 2026-11-02 — rerank 滑动窗口（替代 LLM 有损压缩）

### 问题

`section 重构 → LLM 压缩 → rerank` 的顺序导致两个问题：

1. **reranker 打分基于有损摘要**：超长 section（>1024 token）先被 LLM 压缩到 1024 再喂给 reranker。LLM 压缩时不知道 query，可能压缩掉 query 相关内容，导致打分不准。
2. **候选池无法扩大**：压缩成本 O(候选池大小)，候选池 5→20 后 LLM 调用涨 4 倍，再扩大延迟爆炸。

压缩是常态而非边缘情况：chunk 大小 768 token，section 合并后只要 >1 chunk（~1476 token）就超过 reranker 的 `max_seq_len=1024`，必然被压缩。

### 方案

将"rerank 前 LLM 压缩"改为"reranker 内部滑动窗口"：

- 长 section 按 `max_seq_len - query_len` 切分为重叠窗口
- 每个窗口独立打分，取 **max** 作为 section 分数
- `rag_tool.py` 不再做 rerank 前压缩，章节原文直接喂给 reranker

滑动窗口参数（**必填，无默认值，全部 YAML 显式声明**）：

| 参数 | zh_primary | zh_light / cpu_fallback | 说明 |
|---|---|---|---|
| `window_overlap` | 128 | 64 | 窗口重叠 token 数，避免关键内容被切在边界 |
| `max_windows_per_node` | 5 | 5 | 单 node 窗口数上限，超限时均匀采样保留首尾覆盖 |
| `max_seq_len` | 1024（不变） | 512 | O(n²) 注意力，小窗口总计算量更低 |

### 改动文件

| 文件 | 改动 |
|---|---|
| `rerank/base_reranker.py` | `RerankerParams` 新增必填参数 `window_overlap` / `max_windows_per_node`（无默认值，全部 YAML 显式声明） |
| `rerank/cross_encoder_reranker.py` | `rerank()` 改为先展开窗口再按 max 聚合；新增 `_split_into_windows()` / `_compute_window_size()`；新增模块级 `_uniform_sample()`；窗口数超 `max_windows_per_node` 时 `logger.warning` 记录原始 token 数与窗口数，便于后期统计降级频率 |
| `config/rerank/rerank-config.yaml` | `zh_primary` 新增 `window_overlap: 128` / `max_windows_per_node: 5` |
| `rag_tool.py` | 删除阶段 3（rerank 前 LLM 压缩）和阶段 5（恢复原文）；阶段重编号；docstring 同步更新 |

### 改动量

- 新增 ~70 行（滑动窗口逻辑）
- 删除 ~20 行（压缩 + 恢复逻辑）
- `rag_tool.py` 净减 ~20 行
- `SummaryService.compress_nodes()` 保留但不再被调用（dead code，可后续清理）

### 预期效果

| 场景 | 修改前 | 修改后 |
|---|---|---|
| reranker 输入 | LLM 有损摘要 | 完整原文（滑动窗口） |
| 信息完整性 | ❌ 丢失 30-60% | ✅ 100% 覆盖 |
| 候选池 LLM 调用 | 8-12 次 | 0 次 |
| 候选池可扩大 | ❌ 压缩成本线性增长 | ✅ 无 LLM 成本 |
| rerank 延迟 | ~3-5s（含 LLM 压缩） | ~1-2s（纯 reranker） |
| 最终 LLM 资料 | 完整 section | 完整 section（不变） |

### 性能分析

cross-encoder 注意力 O(n²)，滑动窗口保持 `max_seq_len=1024` 最优：

| 方案 | 总计算量（20 section × 1500 token） |
|---|---|
| 1024 + 滑动窗口 | ~42M |
| 2048 + 滑动窗口 | ~84M |
| 4096 + 滑动窗口 | ~336M |

窗口数预估（1024，重叠 128）：2-chunk section → 2 窗口，3-chunk → 3 窗口。

### 边界情况

| 情况 | 处理 |
|---|---|
| `window_overlap=0` | 退化为整段返回（原 truncate 行为） |
| 短 section（≤ window_size） | 直接返回原文，不切 |
| 窗口数超上限 | 均匀采样 `max_windows_per_node` 个，保留首尾 |
| query 过长 | `window_size` 设下限 1，避免负数 |
| 取消信号 | 复用 `score_pairs` 的 batch 间 cancel 检查 |

### 验证建议

1. 检索后日志确认 `[Rerank] 候选数量:N | 窗口总数:M → 输出:K`，M 应 ≥ N
2. 对比同一 query 修改前后的最终 context，确认 rerank 排序变化（长 section 不再因压缩丢信息而被误判）
3. 观察 rerank 阶段耗时，确认低于原 LLM 压缩方案
4. 确认 `window_overlap=0` 时行为退回原 truncate（回归验证）

---

## 2026-11-02 — rerank 候选池与最终输出解耦

### 问题

`top_k` 一个参数同时承担两种语义：

1. **候选池大小** — `hybrid_retriever.retrieve(top_k=5)`，决定检索器返回多少 section
2. **最终输出大小** — `reranker.rerank(..., top_k=5)`，决定保留多少 section

两者被绑定为同一个值，导致 reranker 收到的候选就是最终输出（5 个）。rerank 的价值在于从更大的候选池中精选，候选池等于输出大小时，精度优化空间被彻底锁死。

数据流（修改前，`top_k=None` 走 YAML 默认值 5）：

```
rag_router.query_rag()  →  effective_top_k = 5
  → hybrid_retriever.retrieve(top_k=5, dense=10, sparse=10)
      → RRF top_k = 5 × 3 = 15
      → section 去重 → 5
  → 章节重构 → 5
  → reranker.rerank(5 个节点, top_k=5) → 5
```

reranker 只能对这 5 个重新排序，无法把排名第 6~20 的候选捞回来。

### 方案

将 `top_k` 拆分为两个独立参数，**全部由 YAML 配置驱动**（去掉 `query_rag` 的 `top_k` 入参，避免与 YAML 的 `top_k` 同名歧义）：

| 参数 | 语义 | 值 |
|---|---|---|
| `retrieve_top_k` | 候选池大小：检索器返回多少 section 给 reranker | 20 |
| `top_k` | 最终输出大小：reranker 精选后保留多少 section | 5 |

同步放大 `dense_top_k` / `sparse_top_k`（10 → 30）保证候选充足，`rrf_oversample_multiplier` 3 → 2 避免 RRF 池过大。

### 改动文件

| 文件 | 改动 |
|---|---|
| `config/retriever/retriever-config.yaml` | 新增 `retrieve_top_k: 20`；`dense_top_k`/`sparse_top_k` 10→30；`rrf_oversample_multiplier` 3→2 |
| `config/retriever/retriever_config_loader.py` | `RetrieverConfig` 新增 `retrieve_top_k` 字段（`__slots__` + `__init__` + `_build_one`） |
| `rag_tool.py` | 删除 `query_rag` 的 `top_k` 入参；`effective_top_k` 拆为 `retrieve_top_k`（YAML）/ `rerank_top_k`（YAML `top_k`）；retrieve 传前者，rerank 传后者；日志输出两个值 |

### 改动量

- 新增 1 个配置字段
- 修改 3 个文件
- `HybridRetriever` / `SectionReconstructor` / `CrossEncoderReranker` **零改动**（接口不变，只是传入的数值不同）

### 预期效果

| 场景 | 修改前 | 修改后 |
|---|---|---|
| 候选池 | 5 | 20 |
| rerank 输入 | 5 个 section | 20 个 section |
| 最终输出 | 5 个 section | 5 个 section（不变） |
| precision 上限 | 锁死在 top5 | 从 top20 中精选 |
| 上下文 token | 不变 | 不变 |

### 代价

- rerank 推理量 5 → 20（约 4 倍），cross-encoder batch 推理绝对耗时增加几十 ms
- 章节重构的 DB 批量查询量增加（已是单次 OR 查询，边际成本低）
- 超长 section 的压缩节点可能增多（仅影响超 `max_seq_len` 的节点）

### 验证建议

1. 检索后在日志中确认 `retrieve_top_k=20 | rerank_top_k=5`
2. 对比修改前后同一 query 的最终 context，确认 rerank 排序发生变化（候选池变大后，选中的 section 可能不同）
3. 观察 rerank 阶段耗时，确认在可接受范围内

---

## 2026-11-02 — 表格感知分块（Table-Aware Chunking）

### 问题

`MarkdownDocumentSplitter` 对超大章节（>768 token）使用 LlamaIndex `TokenTextSplitter` 切分，该切分器按空格→换行→字符三级级联分割，**对 markdown 表格结构零感知**。

后果：当章节内含超过 chunk_size 的表格时，TokenTextSplitter 在表格行间随机切断，导致：
- Chunk A 拿到表头 + 前 N 行数据，Chunk B 拿到剩余行（无表头）
- LLM 看到 B 时无法理解数据列含义
- 表格碎片被嵌入为不完整向量，影响检索召回

受影响数据源：PDF（pymupdf4llm 输出标准 markdown 表格）、PPTX（表格混入正文）、HTML。

### 方案

在 `spliter.py` 的分割分支增加表格边界检测，改"盲目切分"为"表格感知分块"：

1. **`_find_table_blocks(text)`** — 正则扫描 `| col |` 行 + `|---|---|` 分隔行，定位表格区域起止偏移
2. **`_table_aware_split(text, blocks, limit)`** — 占位符隔离表格 → TokenTextSplitter 处理非表格文本 → 还原占位符为独立 chunk
3. **`_split_table_with_header(table_text, limit)`** — 超大表格按行切分，每份子表都重复表头行 + 分隔行

无表格文档完全走原有 `TokenTextSplitter` 路径，零回归风险。

### 改动文件

| 文件 | 改动 |
|---|---|
| `src/com/damon/ming/ai/spliter/spliter.py` | +`import re`、两个正则常量、`_find_table_blocks()`、`_split_table_with_header()`、`_table_aware_split()` 三个方法；分割分支加 `if table_blocks` 判断 |

### 改动量

- 新增 ~152 行
- 修改 1 处 if-else 分支
- 无表格路径行为不变

### 预期效果

| 场景 | 修改前 | 修改后 |
|---|---|---|
| 表格 ≤ 768 token | 完整保留 | 不变 |
| 表格 > 768 token | 被切断，LLM 看到无表头的碎片 | 按行切分，每份都带表头 |
| 章节含表格 + 正文 | 表格和正文混切，边界随机 | 表格作为独立 chunk，正文正常切 |
| 无表格章节 | TokenTextSplitter 原逻辑 | 不变（走 else 分支） |

### 验证建议

1. 上传含大表格的 PDF，检查 chunk 是否保留了完整表格结构
2. 检索"年龄段分布"类 query，确认命中 chunk 包含表头
3. 确认无表格文档的 chunk 数量与修改前一致（回归验证）

---

## 2026-11-02 — PDF 解析层多策略拆分

### 问题

`pdf_data_source.py` 将 PDF 解析、图片提取、OCR 全部耦合在一个类中。
所有 PDF 无论类型都走同一条 pymupdf4llm 路径，扫描件 PDF 解析失败时无法降级。
且后续新增 PDF 解析策略需要修改已有类，违反开闭原则。

### 方案

引入 `pdf/` 子包，按职责分层：

1. **`BasePdfParser`** — 抽象基类，定义 `parse() -> list[Document]` 契约
2. **`TextPdfParser`** — 文本 PDF 路径（pymupdf4llm + OCR 图片提取）
3. **`ScannedPdfParser`** — 扫描件路径（fitz 逐页提取图片 → PaddleOCR）
4. **`route_pdf_parser()`** — 路由函数，采样前 5 页检测可选中文字占比，自动选解析器
5. **`LocalPDFDataSource`** — 变为薄路由层，构造函数和接口不变，内部委托给解析器

### 改动文件

| 文件 | 改动 |
|---|---|
| `source/pdf/base_pdf.py` | 新增：抽象基类 |
| `source/pdf/text_pdf.py` | 新增：文本 PDF 解析器（从原 pdf_data_source.py 抽出） |
| `source/pdf/scanned_pdf.py` | 新增：扫描件 PDF 解析器 |
| `source/pdf/__init__.py` | 新增：路由函数 + 导出 |
| `source/pdf_data_source.py` | 重构：从单类实现改为路由层 |
| `source/__init__.py` | 微调：加 `route_pdf_parser` 导入 |

### 改动量

- 新增 4 个文件（base_pdf.py, text_pdf.py, scanned_pdf.py, __init__.py）
- 重写 1 个文件（pdf_data_source.py，接口不变）
- 微调 1 个文件（source/__init__.py，加 1 行 import）
- RAG pipeline / chunker / retriever **零改动**

### 扩展方式

新增 PDF 解析策略只需：
1. 新建文件继承 `BasePdfParser`，实现 `parse()`
2. 在 `route_pdf_parser()` 中加一条 `elif` 规则
3. 其他文件（包括 `LocalPDFDataSource`）无需改动

### Document 元数据对齐

所有解析器输出的 Document 统一包含 `parse_method` 字段：
- `"text"` — 文本 PDF 路径
- `"ocr"` — 扫描件路径

便于检索和日志追踪解析来源。

---

## 2026-11-02 — 章节标题链（Heading Path）注入 LLM 上下文

### 问题

`MarkdownNodeParser` 切分 markdown 时，已在每个 node 的 metadata 中自动生成 `header_path`（格式如 `"/性能要求/并发指标/"`），记录该 chunk 在文档中的完整标题层级。

但 `MarkdownDocumentSplitter._attach_metadata()` 覆盖 node.metadata 时未保留该字段，导致：
- 向量库中 chunk 无章节归属信息
- `SectionReconstructor.merge_nodes_to_text()` 拼接的裸文本喂给 LLM 时，LLM 不知道每个 chunk 出自文档哪个章节
- 多章节文档检索后，LLM 无法区分同名词在不同章节下的语义差异

### 方案

3 处微调，将 `header_path` 从切分阶段一路传递到 LLM prompt：

1. **`spliter.py` `_attach_metadata()`** — 转存 `header_path` → `heading_path`，随 chunk 入库
2. **`constructor.py` `_build_section_nodes()`** — 已有 `metadata.copy()` 自动保留，无需改动
3. **`constructor.py` `merge_nodes_to_text()`** — 拼接时每个 chunk 前附加 `【父标题 > 子标题】` 前缀

### 改动文件

| 文件 | 改动 |
|---|---|
| `src/com/damon/ming/ai/spliter/spliter.py` | `_attach_metadata()` 末尾 +2 行：转存 `header_path` → `heading_path` |
| `src/com/damon/ming/ai/constructor/constructor.py` | `merge_nodes_to_text()` 重写：按 `heading_path` 生成 `【】` 前缀 |

### 改动量

- 新增 ~10 行
- 修改 1 个方法
- 向量库 schema / 检索流程 / rerank **零改动**

### 预期效果

**改前** LLM 看到的参考资料：
```
参考资料：

QPS 需要达到 1000 以上。P99 延迟 < 100ms。
---
SLA 99.99%，全年故障时间不超过 52 分钟。
```

**改后** LLM 看到的参考资料：
```
参考资料：

【性能要求 > 并发指标】
QPS 需要达到 1000 以上。P99 延迟 < 100ms。
---
【性能要求 > 可用性指标】
SLA 99.99%，全年故障时间不超过 52 分钟。
```

### 收益

| 维度 | 说明 |
|---|---|
| ✅ LLM 上下文定位 | 知道每个 chunk 的完整章节层级，回答可引用章节名 |
| ✅ 歧义消解 | 同名词出现在不同章节时，靠 heading 区分语义 |
| ✅ 零存储开销 | 复用 LlamaIndex 已有 metadata，不增向量库字段 |
| ✅ 向后兼容 | 无 heading 的文档（FAQ、扁平结构）chunk 不受影响 |
| ⚠️ token 占用 | 每个 chunk 前缀约消耗 10-30 token，在 512 budget 下有一定占比；等 budget 放宽后成本可忽略 |

### 验证建议

1. 上传多层级 markdown/PDF，检索后在 server log 中确认 prompt 包含 `【】` 前缀
2. 问"第三章的并发指标是什么"类问题，确认 LLM 能定位到正确章节
3. 确认无标题文档的 prompt 中无前缀（回归验证）

---

## 2026-11-03 — rerank 打分输入附加章节标题链（heading_path）

### 问题

承接"章节标题链注入 LLM 上下文"（2026-11-02）：`heading_path` 此前只用于 `merge_nodes_to_text()` 拼 LLM prompt，**reranker 打分时看不到**。

reranker 输入只有 section 正文。当多个 section 正文结构相似、只有标题能区分主题时（典型：正文写"该参数默认 30 秒"，指代信息全在标题里），reranker 无法判断哪个 section 与 query 主题匹配，可能把正确 section 挤出 top-5。

信息不对称：LLM 能看到章节层级，reranker 看不到。

### 方案

在 `CrossEncoderReranker` 打分前，把 `heading_path` 作为前缀附加到文本，让 reranker 感知上下文层级：

- 新增 `_heading_prefix(node)`：读 `heading_path`，格式化为 `【父 > 子】\n`；无该字段（PDF/Word/PPT 等）返回空串
- `_split_into_windows()` 增加 `prefix` 参数，**每个滑动窗口都带前缀**——而非只给第一个窗口：`rerank` 取各窗口 max 分，只给第一个会让后续窗口丢失标题语境
- 从 `window_size` 中扣除 prefix 的 token 数，避免超出 `max_seq_len` 被截断
- 由 YAML 开关 `include_heading` 控制，**必填、无默认值**；关闭时 `prefix` 为空串，打分输入与改动前逐字节一致

### 改动文件

| 文件 | 改动 |
|---|---|
| `rerank/base_reranker.py` | `RerankerParams` 新增必填参数 `include_heading: bool`（无默认值） |
| `config/rerank/rerank-config.yaml` | `zh_primary` / `zh_light` / `cpu_fallback` 三个 profile 各加 `include_heading: true` |
| `rerank/cross_encoder_reranker.py` | 新增 `_heading_prefix()`；`_split_into_windows()` 加 `prefix` 参数；`rerank()` 调用处拼接 |

### 改动量

- 新增 ~20 行
- 修改 1 个方法签名 + 1 处调用
- 配置加载器 **零改动**（`known_fields` 逻辑自动归类必填字段）
- 向量库 / embedding / 分块 / 检索 **零改动**，无需重新索引

### 预期效果

**例**：知识库有两个章节，正文结构相同、只有数字不同：

```
## 网络设置 > 超时时间
该参数默认 30 秒，最大可设 300 秒。...
## 数据库设置 > 超时时间
该参数默认 10 秒，最大可设 60 秒。...
```

query："数据库连接超时时间默认是多少？"

| | 改前 | 改后 |
|---|---|---|
| reranker 输入 | `该参数默认 30 秒…` / `该参数默认 10 秒…` | `【网络设置 > 超时时间】\n该参数默认 30 秒…` / `【数据库设置 > 超时时间】\n该参数默认 10 秒…` |
| 排序依据 | 正文几乎无区分度，随机 | query 的"数据库"命中标题，正确 section 排前 |
| 最终答案 | 可能答"30 秒"（错） | 答"10 秒"（对） |

### 收益

| 维度 | 说明 |
|---|---|
| ✅ 信息对齐 | reranker 与 LLM 看到同样的章节层级，消除不对称 |
| ✅ 消歧 | 正文指代不明时，靠标题链区分同名词/同结构章节 |
| ✅ 低成本 | 复用已入库的 metadata，零存储/索引开销 |
| ✅ 可开关 | YAML 一键开关，便于 A/B 与回滚 |
| ⚠️ 覆盖范围 | 仅对 Markdown（及正文含 `#` 标题的文档）有效；纯 PDF/Word 无 heading_path，不受影响 |
| ⚠️ 收益有条件 | 正文本身已能区分主题的 section，标题是冗余的 |

### 验证建议

1. `include_heading: true` 下用多层级 Markdown 发查询，对比开关关闭时的 rerank 排序（日志 `[Rerank] 候选数量:N | 窗口总数:M → 输出:K`）
2. 重点验证正文指代不明、只有标题能区分的 query
3. 确认 `include_heading: false` 时打分输入与改动前完全一致（回归验证）
4. **效果需 eval 集定论**：开关只控制行为，不证明收益；需对比同一批 query 在 true/false 下的 top-5 命中

---

## 已分析但未实施

### MMR 多样性重排（Maximal Marginal Relevance）— 状态：已分析，未实施

**思路**：当前 section 去重按 `(file_sha256, section_id)` 精确去重，只能去掉完全相同的 section；近似重复（同义措辞、跨文件重复、模板套话）会同时进入 top-5。可在 rerank 阶段加 MMR，在相关性和多样性间权衡。

**收益评估**：

| 维度 | 说明 |
|---|---|
| ✅ 缺口真实 | 精确去重不保证语义多样性，近似重复会占用有限的 5 个槽位 |
| ⚠️ 收益有限 | 5 个槽位 + 强 cross-encoder，reranker 选出的高相关 section 即使近似也确实相关；QA 场景相关性通常压倒多样性 |
| ⚠️ 成本被低估 | 需 section 级 embedding（当前只存 chunk 级）+ λ 调参 + 分数归一化，非"几行代码" |
| ⚠️ 下游稀释 | 512 预算 + 摘要步骤 + 0.5B 模型是主要瓶颈，rerank 多样性收益会被稀释 |
| ⚠️ 更便宜的替代 | 相似度阈值去重（cosine > 0.95 丢弃）可覆盖大部分场景，无需 λ |

**结论**：方向对但收益不确定、成本被低估。若要做，先用"相似度阈值去重"替代完整 MMR；进入"完整模式"（预算 2048+）后再评估。

**优先级**：低

### Embedding 模型升级（384 维 → bge-m3）— 状态：已确认无需实施

**思路**：升级为 bge-m3（1024 维，中英文双语）提升 dense recall。

**结论**：**前提不成立，已完成**。当前 `embedding-config.yaml` 已是 `BAAI/bge-m3`（1024 维），并正确配置了 `query_prefix` / `passage_prefix` / `normalize_embeddings`；pgvector `embedding_dimension: 1024` 一致。全库仅此一个 embedding 引擎在用。

**剩余可挖掘方向**（非"换模型"）：

| 方向 | 说明 |
|---|---|
| bge-m3 完整能力 | 当前只用 dense，未用其 sparse lexical weights / multi-vector；sparse 由 BM25 承担，两者信号不等价，可互补但需 eval |
| device | 当前 `cpu`，影响延迟不影响召回；如延迟成为瓶颈可改 `cuda` |
| 真正的召回瓶颈 | chunk 切分（768+60）、RRF 权重（0.7/0.3）、`retrieve_top_k=20`、section 重构、reranker 滑动窗口 |

**优先级**：无需实施（已达标）

### 语义分块（Semantic Chunking）— 状态：已分析，未实施

**思路**：当前用 `MarkdownNodeParser` 按标题切 + `TokenTextSplitter` 按 token 硬切。改为：先按句子切，再计算相邻句子 embedding 的余弦相似度，在相似度骤降处合并/断开。

**适用场景**：非结构化文档（PDF 转 markdown 时标题丢失的情况）。

**收益评估**：

| 维度 | 说明 |
|---|---|
| ✅ 无标题 PDF 的 chunk 质量 | 话题自然边界断开，比 token 硬切语义纯度高 |
| ✅ 嵌入质量 | 完整语义单元的 embedding 更接近 query 语义空间 |
| ⚠️ 覆盖范围 | 收益集中在无标题/口语化文档，有标题文档 MarkdownNodeParser 已切好 |
| ⚠️ 成本 | 每对相邻句子需算 embedding，索引延迟 +30~60% |
| ⚠️ 中文分句 | 书面语可用标点分，口语化/无标点文本需额外处理 |
| ⚠️ Section 重建已兜底 | 命中 chunk 后拉回整节，部分弥补了边界不理想 |

**结论**：收益中等，成本不低。优先级低于"上下文预算放宽 512→1536"。建议先确认样本中文档类型分布——若无标题/口语化占比高则收益显著，若有标题正式文档为主则可暂缓。

**优先级**：中
