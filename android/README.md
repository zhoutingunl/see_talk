# SeeTalk Android(WebView 套壳)

把电脑上跑的 SeeTalk Web 应用装进一个原生外壳,在手机上验证最终效果。
壳很薄(一个 `MainActivity`),所有功能仍由 Web 端提供;关键是补齐了**摄像头/麦克风权限**与**自签 HTTPS**,这正是普通套壳缺的部分。

## 为什么必须 HTTPS
WebView 里 `getUserMedia`(摄像头/麦克风)只在**安全上下文**可用。手机访问电脑的局域网 IP 属非安全上下文,所以后端必须以 **https** 提供;本壳已处理自签证书(开发期自动接受)。
> 注:WebView 不支持浏览器内置语音识别(Web Speech),所以语音走**百炼 ASR**(`/api/asr`,服务端)。请确保后端配了 `BAILIAN_API_KEY`。

## 运行步骤

### 1. 电脑上启动后端(HTTPS)
```bash
cd see_talk
SEETALK_HTTPS=1 python3.11 app.py      # 监听 https://0.0.0.0:8000
```
查电脑局域网 IP(手机要连得到):
```bash
ipconfig getifaddr en0                  # 例如 192.168.1.10
```
确保手机和电脑**同一 Wi-Fi**,且电脑防火墙放行 8000 端口。

### 2. Android Studio 打开并运行
1. Android Studio → **Open** → 选 `see_talk/android/` 目录。
2. 等待 Gradle Sync(首次会下载 AGP 8.1 / Gradle 8.2,需联网)。
   - 已对齐本机 SDK:compileSdk 34、build-tools 34;如提示缺组件,点提示安装即可。
3. 手机用 USB 连接电脑并开启「USB 调试」(或用无线调试)。
4. 点 ▶ Run,选你的手机。

### 3. 在手机上
1. 首次启动会让你输入服务器地址,填:`https://192.168.1.10:8000`(换成你电脑的 IP)→ 连接。
2. 系统弹窗授予**摄像头**和**麦克风**权限。
3. 自签证书:本壳已自动接受(无需手动)。
4. 开始用:默认**后置摄像头**(看世界),语音走百炼。顶部菜单(右上三点)可「更换服务器地址 / 刷新」。

## 命令行装 APK(可选)
若装了命令行工具,也可不用 IDE:
```bash
cd android
./gradlew assembleDebug                 # 产物:app/build/outputs/apk/debug/app-debug.apk
adb install -r app/build/outputs/apk/debug/app-debug.apk
```
> 仓库未含 `gradle-wrapper.jar`(二进制)。用 Android Studio 打开会自动补齐;命令行可先 `gradle wrapper --gradle-version 8.2` 生成。

## 排错
- **打不开摄像头/麦克风**:确认 ① 用的是 `https://`(非 http);② 已授予系统权限;③ 后端确实以 HTTPS 启动。
- **连不上**:同一 Wi-Fi?IP 对吗?防火墙放行 8000?
- **语音不识别**:后端需配 `BAILIAN_API_KEY`(WebView 没有浏览器语音兜底)。
- **TTS 不出声**:已设 `mediaPlaybackRequiresUserGesture=false`;若仍无声,先点一下页面再试。

## 这个壳做了什么(对比普通套壳)
| 能力 | 处理 |
| --- | --- |
| 网页请求摄像头/麦克风 | `WebChromeClient.onPermissionRequest` 授予 |
| 系统运行时权限 | 启动申请 CAMERA / RECORD_AUDIO |
| 自签 HTTPS | `onReceivedSslError` 接受 + networkSecurityConfig 信任 user 证书 |
| TTS 自动播放 | `mediaPlaybackRequiresUserGesture=false` |
| session_id(A/B) | `domStorageEnabled` 开启 localStorage |
| 返回键 | WebView 后退 |
| 前台不锁屏 | `FLAG_KEEP_SCREEN_ON`(仅前台生效、无需权限;摄像头演示不被自动锁屏打断) |

> 关于后台/熄屏运行:Android 9+ 禁止后台访问摄像头,麦克风后台需前台服务(microphone 类型)+ 常驻通知,
> 既脆弱又依赖系统版本。本壳只做"前台常亮"这个简单可靠方案;如需熄屏后台采集,另行加前台服务。
