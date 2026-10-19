# app-server/src/com/damon/ming/ai/source/__init__.py
"""
数据源抽象层 —— 引擎自注册 + 解析接口。

添加新数据源：
  1. 新建引擎类，继承 BaseDataSource
  2. 使用 @register_engine("name") 装饰器
  3. 在本文件底部 import 引擎类（触发注册）
"""

from src.com.damon.ming.ai.source.base import BaseDataSource

# ── 引擎注册表（必须在实现类 import 之前定义）──────────────────────
_name_to_class: dict[str, type[BaseDataSource]] = {}


def register_engine(name: str):
    """数据源引擎注册装饰器。

    使用方式：
        @register_engine("pdf")
        class LocalPDFDataSource(BaseDataSource):
            ...

        @register_engine("text")
        class LocalTextDataSource(BaseDataSource):
            ...

    装饰时校验继承关系并加入注册表。
    """

    def decorator(cls: type[BaseDataSource]):
        if not issubclass(cls, BaseDataSource):
            raise TypeError(
                f"{cls.__name__} 必须继承 BaseDataSource 才能注册为数据源引擎"
            )
        _name_to_class[name] = cls
        return cls

    return decorator


def resolve_source(engine: str) -> type[BaseDataSource]:
    """根据引擎名解析数据源实现类。"""
    if engine not in _name_to_class:
        raise ValueError(
            f"未知数据源引擎: '{engine}'，可用引擎: {list(_name_to_class.keys())}"
        )
    return _name_to_class[engine]


def list_engines() -> list[str]:
    """列出所有已注册的数据源引擎名。"""
    return list(_name_to_class.keys())


# ── 触发注册（必须放在注册器定义之后）──────────────────────────────
from src.com.damon.ming.ai.source.csv_data_source import LocalCsvDataSource
from src.com.damon.ming.ai.source.doc_data_source import LocalDocDataSource
from src.com.damon.ming.ai.source.html_data_source import LocalHtmlDataSource
from src.com.damon.ming.ai.source.markdown_data_source import LocalMarkdownDataSource
from src.com.damon.ming.ai.source.pdf_data_source import LocalPDFDataSource
from src.com.damon.ming.ai.source.pptx_data_source import LocalPptxDataSource
from src.com.damon.ming.ai.source.text_data_source import LocalTextDataSource
from src.com.damon.ming.ai.source.xlsx_data_source import LocalXlsxDataSource

__all__ = [
    "BaseDataSource",
    "LocalCsvDataSource",
    "LocalDocDataSource",
    "LocalHtmlDataSource",
    "LocalMarkdownDataSource",
    "LocalPDFDataSource",
    "LocalPptxDataSource",
    "LocalTextDataSource",
    "LocalXlsxDataSource",
    "list_engines",
    "register_engine",
    "resolve_source",
]
