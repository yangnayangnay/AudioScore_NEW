import uvicorn
from server.config import CFG

if __name__ == "__main__":
    from server.engines import available_backends
    print("=" * 50)
    print("可用转写后端:")
    for b in available_backends():
        print(f"  {'[OK] ' if b['available'] else '[缺失]'} {b['name']:<22} {b['desc']}")
    print("=" * 50)
    uvicorn.run("server.main:app", host=CFG["server"]["host"],
                port=CFG["server"]["port"], reload=False)
