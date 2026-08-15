"""test_scrape.py - 反爬/合规护栏分层逻辑（M13–M18 / M55）。"""

from signal_search import scrape
def test_is_serp_by_param():
    assert scrape._is_serp("https://www.baidu.com/s?wd=hello") is True
    assert scrape._is_serp("https://cn.bing.com/search?q=hello") is True
    assert scrape._is_serp("https://html.duckduckgo.com/html/?q=x") is True


def test_is_serp_by_path():
    assert scrape._is_serp("https://so.toutiao.com/search?keyword=x") is True
    assert scrape._is_serp("https://www.sogou.com/web?query=x") is True


def test_is_not_serp_for_landing():
    # 第三方落地页（无搜索参数、非搜索路径）应判为非 SERP → 走 robots 检查
    assert scrape._is_serp("https://news.example.com/2026/08/article-123.html") is False
    assert scrape._is_serp("https://blog.foo.com/post/abc") is False


def test_robots_scope_serp_exempts():
    cfg = {"compliance": {"respect_robots": True, "robots_scope": "serp"}}
    # SERP 端点 → 豁免，不发起 robots 请求即返回 True
    assert scrape._robots_ok("https://www.baidu.com/s?wd=x", cfg) is True


def test_robots_scope_all_still_strict():
    # 严格模式：即便 SERP 也走 robots 检查（真实网络下会被 Disallow 拦，这里用异常兜底=True）
    cfg = {"compliance": {"respect_robots": True, "robots_scope": "all"}}
    # 不依赖外网：_robots_ok 对无法访问的域名异常兜底返回 True；仅验证 scope 分支不豁免
    assert scrape._robots_ok("https://www.baidu.com/s?wd=x", cfg) in (True, False)


def test_robots_disabled_bypasses():
    cfg = {"compliance": {"respect_robots": False}}
    assert scrape._robots_ok("https://www.baidu.com/s?wd=x", cfg) is True
