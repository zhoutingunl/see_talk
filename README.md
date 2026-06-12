# SeeTalk · AI 视觉对话助手

实时多模态 AI 对话助手:打开摄像头与麦克风,让 AI 看见环境、听见用户、自然回应。
完整设计见 [`design.md`](./design.md)。

## 架构一句话

浏览器(粗闸门:限帧 / VAD / 抓帧)→ Flask(细闸门:OCR 路由 / 变化检测 / 缓存 / 上下文)
→ **MiniMax-M3 多模态**(Anthropic 兼容直连,真看像素)。ASR 桌面用浏览器 Web Speech、
移动用百炼;TTS 浏览器免费 / 百炼高音质。唯一主要付费项是 M3 图片 token,所有省钱手段都削它。

## 当前进度(PR1)

最小「**抓帧 → 提问 → 回答**」闭环,验证多模态架构成立:

- ✅ Flask 骨架 + `AIService`(M3 直连多模态 + Mock 降级层)
- ✅ 前端开摄像头、按需抓 1 帧(降分 512px)、文字提问、显示回答与 token
- ✅ 无 Key 时自动 Mock,项目照常可跑(产出明确标注"降级示例",不冒充)
- ⏭ 语音(VAD + 百炼/WebSpeech ASR、首句优先 TTS)、成本 Dashboard、OCR 路由 → 后续 PR

## 运行

```bash
pip install -r requirements.txt
cp .env.example .env          # 可选:填入 MINIMAX_API_KEY;不填则 Mock 模式
python3.11 app.py             # http://localhost:8000
```

浏览器打开后:点「开启摄像头」→ 举起物体 → 输入问题 → 提问。
顶部徽标显示当前是「M3 已接入」还是「Mock 模式」。

> 注:摄像头需 `https` 或 `localhost` 才能在浏览器开启(getUserMedia 安全上下文限制)。

## 测试

```bash
python3.11 -m pytest -q --cov=. --cov-report=term-missing
```

**实测(本机 Python 3.11):18 passed,覆盖率 96%。**
策略遵循 design.md §22:Mock 云(MiniMax/百炼),只测确定性逻辑(载荷构造、响应解析、
降级、入参校验、图片解析),不测非确定性的 AI 答案本身。未覆盖部分为 gevent 启动入口
与需真实 Key 的初始化分支。

## 目录

```
see_talk/
  app.py            Flask 入口 + /api/ask 闭环
  config.py         env/.env 配置 + PlanConfig 档位
  ai/
    service.py      AIService 统一入口(降级编排)
    minimax.py      MiniMax-M3 多模态客户端(Anthropic /v1/messages)
    mock.py         无 Key 降级层
    types.py        ChatMessage / VisionReply
  templates/index.html  static/app.js  static/style.css
  tests/            pytest(Mock 云,确定性)
```

## 安全

密钥只存服务端(`.env`,已 gitignore),前端不可见;百炼 wss 由 Flask 代理。
隐私:按需抓帧 + 默认不落盘原始媒体,UI 常驻「正在看」指示(design.md §25)。
