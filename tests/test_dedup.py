from signal_search import rank as dedup  # dedup 已并入 rank
def test_exact_url_dedup():
    docs = [
        {"url": "https://a.com", "snippet": "内容一", "title": "t1"},
        {"url": "https://a.com", "snippet": "内容一重复", "title": "t1"},
        {"url": "https://b.com", "snippet": "内容二", "title": "t2"},
    ]
    out = dedup.near_dup(docs)
    urls = [d["url"] for d in out]
    assert urls.count("https://a.com") == 1
    assert "https://b.com" in urls


def test_simhash_near_dup():
    # 内容完全相同、url 不同 → 近似重复（汉明距=0）应合一
    shared = "苹果产业链 立讯精密 歌尔股份 蓝思科技 组装 结构件 声学 模组 连接器 代工 供应商"
    docs = [
        {"url": "u1", "snippet": shared, "title": "t"},
        {"url": "u2", "snippet": shared, "title": "t"},
        {"url": "u3", "snippet": "完全不同的内容 量子计算 拓扑绝缘体 超导", "title": "t3"},
    ]
    out = dedup.near_dup(docs, threshold=5)
    assert len(out) == 2  # 前两条近似应合一
