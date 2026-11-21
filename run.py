import uvicorn
from server.config import CFG

if __name__ == "__main__":
    if not CFG.get("server", {}).get("fast_start", True):
        from server.engines import available_backends
        print("=" * 50)
        print("available backends:")
        for b in available_backends():
            print("  " + ("[OK] " if b["available"] else "[MISS] ") + b["name"])
        print("=" * 50)
    uvicorn.run("server.main:app", host=CFG["server"]["host"],
                port=CFG["server"]["port"], reload=False,
                access_log=False, loop="asyncio", http="h11",
                timeout_keep_alive=5)
