package com.seetalk.app

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.net.http.SslError
import android.os.Bundle
import android.view.Menu
import android.view.MenuItem
import android.webkit.PermissionRequest
import android.webkit.SslErrorHandler
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

/**
 * SeeTalk Android 套壳:WebView 加载电脑上跑的响应式 Web 应用。
 *
 * 与普通套壳的关键区别(本应用必须):
 *  - onPermissionRequest:把摄像头/麦克风授予网页(getUserMedia),否则语音/视觉全哑。
 *  - 运行时 CAMERA / RECORD_AUDIO 权限申请。
 *  - onReceivedSslError:接受自签证书(getUserMedia 需 https 安全上下文,开发期自签)。
 *  - mediaPlaybackRequiresUserGesture=false:TTS 音频可自动播放。
 *  - domStorageEnabled:前端用 localStorage 存 session_id(A/B 分桶)。
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private val prefs by lazy { getSharedPreferences("seetalk", Context.MODE_PRIVATE) }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        webView = findViewById(R.id.webview)
        configureWebView()
        requestMediaPermissions()

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.canGoBack()) webView.goBack() else finish()
            }
        })

        val url = prefs.getString("server_url", "").orEmpty()
        if (url.isBlank()) promptForUrl() else webView.loadUrl(url)
    }

    private fun requestMediaPermissions() {
        val perms = arrayOf(Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO)
        val need = perms.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (need.isNotEmpty()) ActivityCompat.requestPermissions(this, need.toTypedArray(), 1)
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun configureWebView() {
        with(webView.settings) {
            javaScriptEnabled = true
            domStorageEnabled = true
            mediaPlaybackRequiresUserGesture = false
            mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            allowFileAccess = true
        }
        webView.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest) {
                // 网页请求摄像头/麦克风时直接授予(已在系统层申请过运行时权限)
                runOnUiThread { request.grant(request.resources) }
            }
        }
        webView.webViewClient = object : WebViewClient() {
            override fun onReceivedSslError(
                view: WebView?, handler: SslErrorHandler, error: SslError?,
            ) {
                handler.proceed()   // 开发期:接受自签证书(生产请换正式证书)
            }
        }
    }

    private fun promptForUrl() {
        val input = EditText(this).apply {
            hint = "https://192.168.x.x:8000"
            setText(prefs.getString("server_url", "https://").orEmpty())
        }
        AlertDialog.Builder(this)
            .setTitle("SeeTalk 服务器地址")
            .setMessage("输入电脑上 SeeTalk 的地址(需 https,详见 android/README.md)")
            .setView(input)
            .setCancelable(false)
            .setPositiveButton("连接") { _, _ ->
                val url = input.text.toString().trim()
                prefs.edit().putString("server_url", url).apply()
                webView.loadUrl(url)
            }
            .show()
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menu.add(0, 1, 0, "更换服务器地址")
        menu.add(0, 2, 1, "刷新")
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        when (item.itemId) {
            1 -> promptForUrl()
            2 -> webView.reload()
        }
        return true
    }
}
