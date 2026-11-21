from pathlib import Path
HP = Path(r"E:\Code\cs\AudioScore_new\web\index.html")
s = HP.read_text(encoding="utf-8")
OLD = """if(input&&input.parentNode&&input.nextSibling)
  input.parentNode.insertBefore(panel,input.nextSibling);
else document.body.appendChild(panel);"""
NEW = "document.body.insertBefore(panel,document.body.firstChild);"
if OLD in s:
    s = s.replace(OLD, NEW, 1)
    HP.write_text(s, encoding="utf-8")
    print("PASS: 转换队列已移到页面顶部")
elif NEW in s:
    print("SKIP: 已经在顶部了")
else:
    print("FAIL: 没找到插入点,把 F12 Console 报错发我")
