# midi-bridge

本地优先的 AI 音频转 MIDI 服务。参照 [mason369/music-to-midi](https://github.com/mason369/music-to-midi) 的模型选型与工程经验，针对 RTX 4070 做的精简 C/S 实现：FastAPI 后端跑在 PC 上，浏览器（含手机）经局域网访问。

## 特性

- **双转写引擎**
  - **MuScriptor**（Kyutai/Mirelo）：多乐器多轨，真实混音 Multi-F1 47.8（对照 YourMT3+ 21.9），可选 large / medium / small
  - **Basic Pitch**（Spotify）：轻量单轨，秒级出结果，用于链路验证与单乐器素材
- **乐器硬约束**：可选定"只转钢琴+贝斯+鼓"，抑制 MuScriptor 跨分片的乐器身份漂移
- **统一后处理管线**：重叠分片去重（跨 5s 分片重复音符合并）、碎音符过滤（<60ms）、力度重建（原始音频 RMS 包络 → velocity）
- **结果缓存**：以 `sha256(音频)+后端+乐器约束+BPM+后处理参数` 为 key，同参数重复任务秒回
- **GPU 串行锁 + 异步任务队列**：单卡安全，多设备同时提交自动排队
- **手机自适应网页前端**：拖拽上传、进度轮询、一键下载

## 架构

```
浏览器 (web/index.html, 手机/PC)
        │ HTTP (局域网)
        ▼
FastAPI (run.py / server/)
        ├─ /api/jobs        异步任务提交+轮询
        ├─ /api/result      MIDI 下载
        ▼
JobManager (GPU 锁 + 线程池)
        ├─ MuscriptorEngine (subprocess 调 CLI)
        ├─ BasicPitchEngine (进程内常驻)
        ▼
raw MIDI → 统一 Note 模型 → 后处理(去重/过滤/力度) → 缓存 → pretty_midi 写出
```

**核心设计**：引擎层只负责产出 raw MIDI，所有引擎输出统一读入 `Note` 数据模型后再做后处理——后处理代码只写一份，与具体引擎解耦。MuScriptor 走 subprocess（换取进程干净退出、无显存泄漏），Basic Pitch 进程内常驻。

## 环境要求

| 项目 | 要求 |
|---|---|
| 系统 | Windows 10/11（bat 脚本）；Linux/macOS 见手动安装 |
| Python | 3.10 – 3.12 |
| 显卡 | MuScriptor 建议 ≥8GB 显存（4070 8G 用 medium 或 large，12G 无压力）；Basic Pitch CPU 即可 |
| 磁盘 | 基础约 4GB；MuScriptor large 另需约 9GB（权重 5.5GB + cu128 torch 3-5GB） |

## 快速开始

```bat
setup.bat     :: 装依赖; 结束前会询问是否现在配置 MuScriptor (需 HF 账号, 可跳过)
start.bat     :: 启动服务, 自动打开浏览器并打印手机访问地址
```

手机访问：与 PC 连同一 Wi-Fi，浏览器打开 start.bat 窗口里打印的 `http://<PC局域网IP>:8000`。打不开先放行防火墙（管理员 PowerShell）：

```
netsh advfirewall firewall add rule name="midi-bridge" dir=in action=allow protocol=TCP localport=8000
```

## 手动安装（非 Windows / 命令行）

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install basic-pitch                              # 轻量后端

# MuScriptor (可选): 先到 huggingface.co/MuScriptor/muscriptor-large 点接受条款
pip install torch --index-url https://download.pytorch.org/whl/cu128
pip install muscriptor
hf auth login
hf download MuScriptor/muscriptor-large              # 预下载, 避免首次任务"假死"

python run.py
```

## 配置（config.yaml）

| 键 | 说明 | 默认 |
|---|---|---|
| `server.host` | `0.0.0.0` 局域网可访问；`127.0.0.1` 仅本机 | `0.0.0.0` |
| `muscriptor.model` | `large` / `medium` / `small`，**须与已下载权重一致** | `large` |
| `muscriptor.torch_backend` | Windows 填 `cu128`（否则 PyTorch 走 CPU）；Linux 留空 | `cu128` |
| `postprocess.dedup` / `dedup_window_ms` | 重叠分片去重开关 / 合并窗口 | true / 200 |
| `postprocess.filter_short` / `min_note_ms` | 碎音符过滤（鼓豁免） | true / 60 |
| `postprocess.rebuild_velocity` | 力度重建（全局 RMS，非分轨，动态仅供参考） | false |
| `basic_pitch.onset_threshold` / `frame_threshold` | Basic Pitch 灵敏度 | 0.5 / 0.3 |

## 使用技巧

1. **先自动跑一遍**：不勾任何乐器约束提交一次，看 MuScriptor 自动检测出什么；
2. **第二次硬约束**：把漏识别/漂移的乐器勾上（如只勾 piano, bass, drums），乐器身份整曲稳定；
3. **BPM 已知就填**：省去自动检测，MIDI 网格更整齐；
4. **后端选择**：真实混音歌曲 → MuScriptor；哼唱/单乐器/快速验证 → Basic Pitch。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/backends` | 后端可用性 + 乐器列表 |
| POST | `/api/jobs` | multipart：`file`、`backend`、`instruments`(csv)、`bpm` → `{job_id}` |
| GET | `/api/jobs/{id}` | 状态/阶段/耗时/统计，完成时含 `result_url` |
| GET | `/api/result/{id}` | 下载 `.mid` |

```bash
curl -F "file=@song.mp3" -F "backend=muscriptor" \
     -F "instruments=piano,bass,drums" http://localhost:8000/api/jobs
```

## 性能参考（RTX 4070，3 分钟歌曲，量级估计）

| 场景 | 耗时 |
|---|---|
| Basic Pitch | 数秒 |
| MuScriptor medium | 约几十秒 |
| MuScriptor large | 约 1–3 分钟（5s 分片自回归解码 + 每次 10–20s 冷加载） |
| 缓存命中 | <1s |

## 目录结构

```
midi-bridge/
├── setup.bat / start.bat / download_model.bat
├── run.py               # 入口
├── config.yaml
├── requirements.txt
├── server/
│   ├── main.py          # 路由
│   ├── jobs.py          # 任务队列 + GPU 锁
│   ├── cache.py         # 结果缓存
│   ├── midi_io.py       # MIDI ↔ Note
│   ├── postprocess.py   # 去重/过滤/力度重建
│   └── engines/         # base / muscriptor / basicpitch
├── web/index.html       # 单文件前端
├── tmp/  output/  cache/
```

## 已知限制

- MuScriptor 不输出 velocity（重建为全局能量，非分轨）；鼓组仅 onset 不记时值
- 任务表在内存中，服务重启丢失（缓存结果保留在 `cache/`）
- 后处理开关当前为全局配置（`config.yaml`），前端复选框为提示性
- `muscriptor` CLI 参数名（`--instruments`/`--bpm`）以所装版本 `--help` 为准，有出入改 `engines/muscriptor.py` 的 `_build_cmd()`

## 路线图

1. MuScriptor 进程内常驻 + LRU 模型池（省每次 10–20s 冷加载）
2. 每任务后处理参数（前端开关真正生效）
3. BS-RoFormer 六声部分离前置 + 逐 stem 转写
4. 任务 sqlite 持久化
5. FP16 / torch.compile 推理加速

## 致谢与许可

- [MuScriptor](https://muscriptor.kyutai.org)（Kyutai & Mirelo）：权重 **CC BY-NC 4.0（非商用）**，代码 MIT
- [Basic Pitch](https://basicpitch.io)（Spotify）：Apache-2.0
- [mason369/music-to-midi](https://github.com/mason369/music-to-midi)：模型选型与对比数据来源
- 本项目代码：MIT
