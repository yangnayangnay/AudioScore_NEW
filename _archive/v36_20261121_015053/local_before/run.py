import threading

import uvicorn

from server.config import CFG


def _warm_and_list():
    # v28: heavy engine init moved OFF the critical path.
    # Engines are constructed here in background; first transcription
    # job reuses the cached engine, or constructs on demand if user is faster.
    try:
        from server.engines import available_backends
        print("=" * 50)
        print("[后台] 正在初始化转写引擎 (首次 10-90 秒, 不影响服务使用)...")
        for b in available_backends():
            print("  %s %-22s %s" % (
                "[OK] " if b["available"] else "[缺失]", b["name"], b["desc"]))
        print("[后台] 引擎就绪")
        print("=" * 50)
    except Exception as e:
        print("[后台] engine warmup error:", e)


if __name__ == "__main__":
    print("=" * 50)
    print("服务启动中 (引擎后台加载, 通常 3-5 秒即可访问):")
    print("    http://localhost:%s" % CFG["server"]["port"])
    print("=" * 50)
    threading.Thread(target=_warm_and_list, daemon=True).start()
    uvicorn.run("server.main:app",
                host=CFG["server"]["host"],
                port=CFG["server"]["port"],
                reload=False)
