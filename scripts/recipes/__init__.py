"""recipes —— 脏文档预处理 recipe 层接口契约 + registry(v0.4.0)。

定位:在 ingest pipeline 的 G16 文本主导分流之后、frontmatter 注入之前,把
markitdown 的“半脏”输出加工成更适合 ripgrep 字面检索的干净结构化文本。recipe
失败由 ingest 捕获 → fallback markitdown 原版(诚实降级,不阻断 ingest)。

设计(plan §3 D2):接口是 Python 抽象基类,实现内部可 wrap 任何工具(subprocess /
其他 binary / 纯 Python)。registry 默认只注册 baseline;未来加 recipe = 加一个文件
+ 注册一行,不改 ingest.py。这是 tool-agnostic 的落点:接口稳定,实现可换。

明确不做(scope-control,留下个 minor+):动态加载 / 配置驱动 / CLI 注册参数等
“插件框架”化。registry 是一个写死的 dict,不是插件发现机制。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RecipeResult:
    """recipe 加工结果。

    text:加工后文本(applied=False 时等于透传的原文本)。
    applied:是否真做了加工(False = 透传,frontmatter 标 recipe_applied: none)。
    recipe_name:写入 frontmatter recipe_applied 的名字(如 baseline)。
    notes:加工动作摘要,写入 ingest_log 的 notes 字段(便于追溯做了哪几项)。
    """

    text: str
    applied: bool
    recipe_name: str
    notes: str


class Recipe(ABC):
    """recipe 抽象基类。子类必须给 name + applicable + process。"""

    name: str = "recipe"

    @abstractmethod
    def applicable(self, src_path: str, markitdown_text: str) -> bool:
        """判断本 recipe 是否适用该文件。不适用返回 False,ingest 透传 markitdown 原版。"""

    @abstractmethod
    def process(self, src_path: str, markitdown_text: str) -> RecipeResult:
        """加工。任何异常由 ingest 捕获 → fallback markitdown 原版 + frontmatter recipe_applied: failed。"""


# registry:写死 dict,默认只注册 baseline。加 recipe 在此加一行,不引入动态发现。
_REGISTRY = {
    "baseline": "recipes.baseline:BaselineRecipe",
}


def get_recipe(name: str = "baseline") -> Recipe:
    """registry 入口。默认 baseline。未知名字抛 KeyError(由调用方按需处理)。

    实现类用惰性 import(避免 __init__ import baseline 造成的循环 / 重量加载),
    仅在真正取 recipe 时载入对应模块。
    """
    target = _REGISTRY.get(name)
    if target is None:
        raise KeyError(f"unknown recipe: {name!r}(已注册:{sorted(_REGISTRY)})")
    module_name, _, class_name = target.partition(":")
    import importlib

    module = importlib.import_module(module_name)
    recipe_cls = getattr(module, class_name)
    return recipe_cls()
