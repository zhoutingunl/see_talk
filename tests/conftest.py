"""测试全局:用内存 SQLite,避免单测写出 seetalk.db 文件。"""
import os

os.environ.setdefault("SEETALK_DB", ":memory:")
