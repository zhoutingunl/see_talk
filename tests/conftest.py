"""测试全局:用内存 SQLite,避免单测写出 seetalk.db 文件。"""
import os

os.environ.setdefault("SEETALK_DB", ":memory:")
# 测试不需要 gevent monkey-patch(会干扰 pytest);仅生产服务器用
os.environ.setdefault("SEETALK_NO_GEVENT", "1")
