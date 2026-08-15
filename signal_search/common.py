"""signal_search/common.py - 共享基础设施（配置加载 + 通用工具）。

统一约定：
- `load_config`：传入 cfg 则原样返回（支持调用方注入 / 测试 mock）；否则读取与包同级的
  config.json，缺失或损坏时返回 {}（不抛异常，顺带修 connector 缺键崩溃 F12）。
- `BoundedTTLMap`：长跑进程用的有界 TTL 缓存，杜绝全局态"只增不减"。
其它模块用 `from .common import load_config as _load_cfg` 替换本地副本即可。
"""
import os
import re
import json
import time
import threading
from collections import OrderedDict
from typing import Any, Dict, Optional

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

_DOMAIN_RE = re.compile(r"https?://([^/]+)")

# 进程级默认配置单例：load_config() 无参时返回同一对象（双检锁）。
# 作用：① 避免每次 retrieve()/score_source() 重读磁盘 config.json（性能）；
#      ② 使默认 cfg 的 id() 稳定，杜绝「每请求新 dict → 以 id(cfg) 为键的全局缓存只增不减」
#        的内存泄漏（见 clean_sources._ACTIVE_SRCS_CACHE）。
# 约定：返回的是进程内共享单例，调用方不应就地 mutate；需改配置请传入自己的 dict。
# 磁盘文件变更后需重启进程方才生效（符合服务启动期加载惯例）。
_DEFAULT_CFG: Optional[Dict[str, Any]] = None
_DEFAULT_CFG_LOCK = threading.Lock()


def load_config(cfg: Any = None, force_reload: bool = False) -> Dict[str, Any]:
    """返回配置。

    - 传入 cfg：原样返回（支持调用方注入 / 测试 mock）。
    - 无参：返回进程级单例（双检锁缓存，避免每请求重读磁盘 + 稳定 id(cfg)）。
    - force_reload=True：绕过缓存重新读取（只读、不污染单例），供测试模拟「配置文件变更/
      缺失」场景使用；生产环境磁盘变更需重启进程方才生效。
    """
    if cfg is not None:
        return cfg
    if force_reload:
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    global _DEFAULT_CFG
    if _DEFAULT_CFG is None:
        with _DEFAULT_CFG_LOCK:
            if _DEFAULT_CFG is None:
                try:
                    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                        _DEFAULT_CFG = json.load(f)
                except Exception:
                    _DEFAULT_CFG = {}
    return _DEFAULT_CFG


def domain_of(url: str) -> str:
    """从 URL 取小写域名（含端口）；取不到返回空串。"""
    m = _DOMAIN_RE.search(url or "")
    return m.group(1).lower() if m else ""


class BoundedTTLMap:
    """线程安全的有界 TTL 字典：条目到期自动失效，超上限按 FIFO 淘汰。

    用于长跑进程里的全局态（域名封禁表、robots 判定缓存、节流时间戳等）。
    普通 dict/set 在这些场景下只增不减，会造成两类问题：
    1) 内存慢泄漏——域名基数无上界；
    2) 语义错误——一次瞬时 429 会把域名永久拉黑。
    """

    __slots__ = ("_maxsize", "_ttl", "_data", "_lock")

    def __init__(self, maxsize: int = 512, ttl: float = 300.0):
        self._maxsize = max(int(maxsize), 1)
        self._ttl = float(ttl)
        self._data: "OrderedDict[Any, Any]" = OrderedDict()
        self._lock = threading.RLock()

    # -- 内部：调用方必须已持锁 --
    def _purge_expired(self, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        for key in [k for k, (_, exp) in self._data.items() if exp <= now]:
            self._data.pop(key, None)

    def get(self, key: Any, default: Any = None) -> Any:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return default
            value, expire_at = item
            if expire_at <= time.time():
                self._data.pop(key, None)
                return default
            return value

    def set(self, key: Any, value: Any, ttl: Optional[float] = None) -> None:
        with self._lock:
            self._purge_expired()
            if key in self._data:
                self._data.pop(key, None)
            while len(self._data) >= self._maxsize:
                self._data.popitem(last=False)          # FIFO 淘汰最早条目
            self._data[key] = (value, time.time() + (self._ttl if ttl is None else float(ttl)))

    def pop(self, key: Any, default: Any = None) -> Any:
        with self._lock:
            item = self._data.pop(key, None)
            return default if item is None else item[0]

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __contains__(self, key: Any) -> bool:
        return self.get(key, _MISSING) is not _MISSING

    def __len__(self) -> int:
        with self._lock:
            self._purge_expired()
            return len(self._data)


_MISSING = object()
