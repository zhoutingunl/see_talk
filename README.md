# SeeTalk · AI 视觉对话助手

实时多模态 AI 对话助手:打开摄像头与麦克风,让 AI 看见环境、听见用户、自然回应。

> 📋 **评审先看这里**:[`SUBMISSION.md`](./SUBMISSION.md) —— 提交说明/评审导览,含题目要求的两份交付物(用户故事 计划 vs 实现、成本控制 想到 vs 采用)。
> 完整设计见 [`design.md`](./design.md)。

## 界面

<p>
  <img src="docs/screenshots/web-ui.png" width="250" alt="主界面总览" />
  <img src="docs/screenshots/web-chat.png" width="250" alt="多模态对话" />
  <img src="docs/screenshots/dashboard.png" width="250" alt="成本/QoS 看板" />
</p>

左:竖屏主界面(摄像头预览 + 语音/连续分析控件;图为无头测试用摄像头画面)。
中:多模态问答(实时显示来源/路由/token)。
右:`/dashboard` 成本与 QoS **实测对账**(节省率、缓存命中、路由分布、延迟分桶)。

## 演示视频

<video src="https://github.com/zhoutingunl/see_talk/raw/main/demo.mp4" controls width="320"></video>

> 若上方未内联播放,点此查看:▶ [demo.mp4](./demo.mp4)(约 37 秒)。

## 架构一句话

浏览器(粗闸门:限帧 / VAD / 抓帧)→ Flask(细闸门:OCR 路由 / 变化检测 / 缓存 / 上下文)
→ **MiniMax-M3 多模态**(Anthropic 兼容直连,真看像素)。ASR 中文默认百炼 Paraformer(准),
桌面可切免费 Web Speech;TTS 浏览器免费 / 百炼 CosyVoice 高音质。唯一主要付费项是 M3 图片 token,所有省钱手段都削它。

## 功能(现状)

> 演进过程见仓库 PR 历史(20+ 个 `[feat]/[fix]`,逐个真机验证后合入)。下面是当前代码的实际能力。

**视觉**
- MiniMax-M3 原生多模态,直看像素;**按需抓帧**(提问瞬间 1 帧,降分 512px)。
- **后置摄像头优先**(看世界),前/后可切;提示聚焦**手持/前景物体**,避免前置人脸干扰。
- **OCR 优先路由**(`chi_sim+eng` 中英):纯文本场景只发文本省整图 token;无 tesseract 自动退化发图。

**语音**
- **免手 VAD** 断句(静音 1.2s,过短碎片丢弃,避免一句被切两段);用户开口即**打断**当前播报。
- **ASR**:中文默认百炼 Paraformer(准),桌面可切免费浏览器 Web Speech;移动端统一百炼(`/api/asr` 代理,Key 仅服务端)。
- **流式回答 + 首句优先 TTS**:`/api/ask_stream`(SSE)边收边播;TTS 浏览器免费 / 百炼 CosyVoice 高音质,可切。
- **多轮上下文**:`session_store.py` 按会话维护最近 N 轮文本历史并注入每次调用,支持"它/那个/刚才"指代消解(历史只存文本、不回传旧图,省 token)。

**成本控制(实测对账)**
- 省钱杠杆:按需触发 + 变化检测 + 视觉缓存 + 短上下文(默认10轮文本+当前1帧)+ 图像降分 + OCR优先 + VAD门控。
- `/dashboard`:实际 token vs Baseline → **节省率(实测 95%+)**、缓存命中、路由分布、延迟分桶、埋点。
- **A/B 框架**(`experiments.py`,`ocr_first` 变体对比)、**评估框架**(`evaluation.py`,OCR/对话准确率)。

**连续分析(会议辅助)**
- `/api/observe` 逐帧客观描述累积(变化检测跳过静止画面)+ `/api/summary` 交 M3 汇总成纪要。

**工程**
- Flask + gevent(`monkey.patch_all`,避免同步 requests 阻塞导致并发请求失败);无 Key 自动 Mock 降级,不冒充。
- **手机 App**:`android/` WebView 套壳(摄像头/麦克风权限 + 自签 HTTPS + 前台屏幕常亮)。
- Web 竖屏单列(像手机);**105 单测、覆盖率 96%**。

## 运行

```bash
pip install -r requirements.txt
cp .env.example .env          # 可选:填入 MINIMAX_API_KEY;不填则 Mock 模式
python3.11 app.py             # http://localhost:8000
```

浏览器打开后:点「开启摄像头」→ 举起物体 → 输入问题 → 提问。
顶部徽标显示当前是「M3 已接入」还是「Mock 模式」。

> 注:摄像头/麦克风需**安全上下文**才能开启(浏览器限制)。
> - 本机:用 `http://localhost:8000`(localhost 视为安全)即可,**无需 HTTPS**。
> - 手机/局域网:必须 HTTPS。启动时设 `SEETALK_HTTPS=1 python3.11 app.py`,会用 openssl 自动生成自签证书并以 `https://` 提供(自签证书浏览器会提示风险,点继续即可)。
>
> OCR 优先路由需本地 tesseract;中文场景需 `chi_sim` 语言包(放入 tessdata 目录)。
> 缺包时自动退化为发图,功能不受影响。可用 `OCR_LANG` 覆盖语言(默认自动 `chi_sim+eng`)。

## 手机 App(Android)

`android/` 是一个 WebView 套壳工程,把响应式 Web 装进原生壳在手机上验证。
关键是补齐了普通套壳缺的**摄像头/麦克风权限**与**自签 HTTPS**(getUserMedia 需安全上下文)。
用法:电脑 `SEETALK_HTTPS=1 python3.11 app.py` 启动 → Android Studio 打开 `android/` 一键 Run 到手机 → 填电脑的 `https://<IP>:8000`。详见 [`android/README.md`](./android/README.md)。
> WebView 无浏览器语音,故语音走百炼 ASR(需配 `BAILIAN_API_KEY`);默认后置摄像头,适合"看世界"。

## 测试

```bash
python3.11 -m pytest -q --cov=. --cov-report=term-missing
```

**实测(本机 Python 3.11):110 passed,覆盖率 96%。**
未装 `chi_sim` 中文包的环境,2 项中文 OCR 用例会自动 skip(即 108 passed + 2 skipped),属预期。
策略遵循 design.md §22:Mock 云(MiniMax/百炼),只测确定性逻辑(载荷构造、响应解析、
降级、入参校验、图片解析),不测非确定性的 AI 答案本身。未覆盖部分为 gevent 启动入口
与需真实 Key 的初始化分支。

## 目录

```
see_talk/
  app.py            Flask 入口:/api/ask · /api/ask_stream · /api/asr · /api/tts · /dashboard
  config.py         env/.env 配置 + PlanConfig 档位
  vision_cache.py   感知哈希:视觉缓存 + 变化检测(省钱核心)
  metrics.py        SQLite:token 对账 / 节省率 / 延迟分桶 / 埋点
  ocr_service.py    本地 Tesseract OCR(OCR 优先路由)
  session_store.py  会话多轮上下文(最近 N 轮文本历史,注入到每次调用)
  experiments.py    A/B 实验:确定性分桶 + 变体对比
  evaluation.py     评估框架:OCR 准确率 + 对话成功率
  observations.py   连续分析:观察累积 + 变化检测 + 纪要汇总
  ai/
    service.py      AIService 统一入口(降级编排)
    minimax.py      MiniMax-M3 多模态客户端(非流式 + 流式)
    bailian.py      百炼 Paraformer 实时 ASR(DashScope WS)
    bailian_tts.py  百炼 CosyVoice 实时 TTS(DashScope WS)
    mock.py         无 Key 降级层
    types.py        ChatMessage / VisionReply
  templates/        index.html · dashboard.html
  static/           app.js · voice.js(VAD+ASR)· tts.js(首句优先)· style.css
  tests/            pytest(Mock 云,确定性)
  android/          手机 App(WebView 套壳,见 android/README.md)
  design.md · SUBMISSION.md · README.md   设计 / 评审导览 / 本文
```

## 安全

密钥只存服务端(`.env`,已 gitignore),前端不可见;百炼 wss 由 Flask 代理。
隐私:按需抓帧 + 默认不落盘原始媒体,UI 常驻「正在看」指示(design.md §25)。

## AI 协作说明(design.md §27)

本项目在 AI 辅助下开发,如实声明如下。

### 使用的 AI 工具
- **Claude Code**(主力):需求澄清(grill-me 逐项压测设计)、编码、单测、调试、Git/PR 流程。
- 允许的协作工具同 design.md §27:Hermes / Claude Code / Codex / Cursor Agent / OpenHands。

### AI 承担了什么
- 与作者对话打磨 `design.md`(端云分工、成本模型、QoS、隐私等逐条达成共识)。
- 按 design.md §26 的 PR 顺序实现各模块,并配套 Mock 云的确定性单测。
- 接入真实云能力时逐个**真机验证**(M3 多模态/流式、百炼 ASR 语音往返、CosyVoice TTS、缓存命中、OCR 路由、A/B、评估、会议纪要)。

### 人类作者承担了什么
- 提供技术栈约束与真实 API Key;关键产品取舍(平台 / 语音模态 / 付费分层等)由作者拍板。
- 审阅 PR 与合并、把控方向。

### 底线
- **实现与文档一致**:design.md 描述的能力均有对应实现与测试;未实现项在 §5/§6 如实标注。
- **不冒充**:无 Key 时降级产出明确标注「示例 / 降级」;指标以实测为准(Dashboard / 评估框架),不写死伪指标。
- **密钥安全**:AI 全程不将任何 Key 写入仓库,提交前自动扫描兜底。
