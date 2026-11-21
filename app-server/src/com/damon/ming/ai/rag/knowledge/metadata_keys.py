# app-server/src/com/damon/ming/ai/rag/knowledge/metadata_keys.py
"""知识库 Document 和 TextNode 共用的 metadata 字段名。"""

# 文件身份及磁盘位置。
FILE_SHA256 = "file_sha256"  # 文件内容的 SHA-256，用于去重和向量对账。
FILE_PATH = "file_path"  # 文件当前在磁盘上的路径。
FILE_NAME = "file_name"  # 文件名，供日志和检索结果展示。
FILE_ID = "file_id"  # 上传记录 ID，用于按本次上传回滚向量。
SOURCE_REF_ID = "source_refId"  # 数据源文档引用 ID，当前由文件 SHA-256 填充。

# 章节及分块身份。
SECTION_GROUP = "section_group"  # 数据源指定的逻辑分组，仅供切分阶段确定章节边界。
SECTION_ID = "section_id"  # 章节标识，用于检索去重和按章节重建。
SECTION_SEQ = "section_seq"  # chunk 在所属章节内的顺序，从 0 开始。
CHUNK_ID = "chunk_id"  # chunk 标识，与 TextNode.node_id 一致。
TOTAL_CHUNKS_IN_SECTION = "total_chunks_in_section"  # 所属章节的 chunk 总数。

# 页面定位；非分页格式也可把批次或预分块视为一页。
PAGE = "page"  # 数据源页号，从 1 开始。
PAGE_INDEX = "page_index"  # 数据源页面排序序号，从 0 开始。
PAGE_START = "page_start"  # chunk 覆盖的起始页号。
PAGE_END = "page_end"  # chunk 覆盖的末页页号。
TOTAL_PAGES = "total_pages"  # 文件在数据源中的总页数或总批次数。

# 内容结构、位置及重建信息。
CONTENT_TYPE = "content_type"  # 内容类型，例如 table 或 image_text。
HEADER_PATH = "header_path"  # Markdown 解析器生成的标题层级路径。
HEADING_PATH = "heading_path"  # 传给重排和最终上下文的标题路径。
RECONSTRUCTION_SKIP_CHARS = "reconstruction_skip_chars"  # 重建时跳过的重复前缀字符数。
CHAR_START = "char_start"  # 对应区域在合并后文档中的起始偏移，包含此位置。
CHAR_END = "char_end"  # 对应区域的结束偏移，不包含此位置；表格分片可共用范围。
CHUNK_LENGTH = "chunk_length"  # chunk 正文的字符数。
TOKEN_COUNT = "token_count"  # chunk 正文的 token 数。

# 可选来源信息；索引文本和重建结果使用通用标签，不判断具体文件格式。
SOURCE_CONTEXT = "source_context"  # 数据源提供的可检索上下文标签，如工作表名。
SHEET_NAME = "sheet_name"  # XLSX 原始工作表名。
ROW_START = "row_start"  # CSV/XLSX 当前批次的起始数据行号，从 1 开始。
ROW_END = "row_end"  # CSV/XLSX 当前批次的末尾数据行号，包含此行。
SLIDE_INDEX = "slide_index"  # PPTX 原始幻灯片序号，从 0 开始。

# 需要从源 Document 透传到 chunk 和重建后章节的可选字段。
SOURCE_METADATA_KEYS = (SOURCE_CONTEXT, SHEET_NAME, ROW_START, ROW_END, SLIDE_INDEX)
