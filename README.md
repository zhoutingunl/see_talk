# SeeTalk · AI 视觉对话助手

实时多模态 AI 对话助手:打开摄像头与麦克风,让 AI 看见环境、听见用户、自然回应。
完整设计见 [`design.md`](./design.md)。

## 架构一句话

浏览器(粗闸门:限帧 / VAD / 抓帧)→ Flask(细闸门:OCR 路由 / 变化检测 / 缓存 / 上下文)
→ **MiniMax-M3 多模态**(Anthropic 兼容直连,真看像素)。ASR 桌面用浏览器 Web Speech、
移动用百炼;TTS 浏览器免费 / 百炼高音质。唯一主要付费项是 M3 图片 token,所有省钱手段都削它。

## 当前进度

### PR1 · 抓帧问答闭环
- ✅ Flask 骨架 + `AIService`(M3 直连多模态 + Mock 降级层)
- ✅ 前端开摄像头、按需抓 1 帧(降分 512px)、文字提问、显示回答与 token
- ✅ 无 Key 时自动 Mock,项目照常可跑(产出明确标注"降级示例",不冒充)

### PR2 · 语音交互闭环
- ✅ **免手 VAD**:浏览器端能量阈值断句(`static/voice.js`)
- ✅ **ASR 分层**:桌面浏览器 Web Speech(免费)/ 移动端百炼 Paraformer(`/api/asr` 代理,Key 仅在服务端)
- ✅ **流式回答 + 首句优先 TTS**:`/api/ask_stream`(SSE)边收边播(`static/tts.js`)
- ✅ 真机验证:M3 流式 SSE 实时输出;百炼 ASR 语音往返(合成「你好,这是语音识别测试」→ 准确转写)

### PR3 · 成本控制 + Dashboard
- ✅ **视觉缓存 + 变化检测**:感知哈希(average hash),同画面同问命中缓存、零云调用(`vision_cache.py`)
- ✅ **token 实测对账**:每轮记 实际 token vs Baseline(朴素每轮整图),算节省率(`metrics.py`,SQLite)
- ✅ **延迟分桶**(纯文本 / 带图 P50/P95)+ **埋点 EventLog**
- ✅ **Dashboard**:`/dashboard` 实时展示轮数 / 节省率 / 命中率 / 成本估算 / 延迟
- ✅ 真机验证:同图同问第二次命中缓存(token 0)、实测节省率 95.4%

### PR4 · OCR 优先路由
- ✅ **本地 Tesseract OCR**:纯文本场景(报错/英文/代码)先本地 OCR → 只发文本给 M3,省掉整图 token(`ocr_service.py`)
- ✅ 路由判定:字符数 + 置信度阈值;非文本场景仍发降分图;无 tesseract 自动退化为发图
- ✅ Dashboard 新增**路由分布**(ocr/image/cache)
- ✅ 真机验证:英文报错图 → `route=ocr`,input token 72(发图需数百),M3 正确解释 TypeError
- ✅ **中文 OCR**:`chi_sim+eng`,中文文本场景也走 OCR 路由(真机:「系统错误:文件未找到」识别置信度 96%)
- ⏭ 连续分析模式、百炼高音质 TTS、A/B 实验框架 → 后续 PR

## 运行

```bash
pip install -r requirements.txt
cp .env.example .env          # 可选:填入 MINIMAX_API_KEY;不填则 Mock 模式
python3.11 app.py             # http://localhost:8000
```

浏览器打开后:点「开启摄像头」→ 举起物体 → 输入问题 → 提问。
顶部徽标显示当前是「M3 已接入」还是「Mock 模式」。

> 注:摄像头需 `https` 或 `localhost` 才能在浏览器开启(getUserMedia 安全上下文限制)。
>
> OCR 优先路由需本地 tesseract;中文场景需 `chi_sim` 语言包(放入 tessdata 目录)。
> 缺包时自动退化为发图,功能不受影响。可用 `OCR_LANG` 覆盖语言(默认自动 `chi_sim+eng`)。

## 测试

```bash
python3.11 -m pytest -q --cov=. --cov-report=term-missing
```

**实测(本机 Python 3.11):69 passed,覆盖率 96%。**
策略遵循 design.md §22:Mock 云(MiniMax/百炼),只测确定性逻辑(载荷构造、响应解析、
降级、入参校验、图片解析),不测非确定性的 AI 答案本身。未覆盖部分为 gevent 启动入口
与需真实 Key 的初始化分支。

## 目录

```
see_talk/
  app.py            Flask 入口:/api/ask · /api/ask_stream(SSE)· /api/asr · /dashboard
  config.py         env/.env 配置 + PlanConfig 档位
  vision_cache.py   感知哈希:视觉缓存 + 变化检测(省钱核心)
  metrics.py        SQLite:token 对账 / 节省率 / 延迟分桶 / 埋点
  ocr_service.py    本地 Tesseract OCR(OCR 优先路由)
  ai/
    service.py      AIService 统一入口(降级编排)
    minimax.py      MiniMax-M3 多模态客户端(非流式 + 流式)
    bailian.py      百炼 Paraformer 实时 ASR(DashScope WS)
    mock.py         无 Key 降级层
    types.py        ChatMessage / VisionReply
  templates/        index.html · dashboard.html
  static/           app.js · voice.js(VAD+ASR)· tts.js(首句优先)· style.css
  tests/            pytest(Mock 云,确定性)
```

## 安全

密钥只存服务端(`.env`,已 gitignore),前端不可见;百炼 wss 由 Flask 代理。
隐私:按需抓帧 + 默认不落盘原始媒体,UI 常驻「正在看」指示(design.md §25)。
