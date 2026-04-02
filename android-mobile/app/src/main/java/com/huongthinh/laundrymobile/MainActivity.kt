package com.huongthinh.laundrymobile

import android.annotation.SuppressLint
import android.content.SharedPreferences
import android.graphics.Bitmap
import android.os.Bundle
import android.view.View
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.ProgressBar
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var edtUrl: EditText
    private lateinit var btnLoad: Button
    private lateinit var progressBar: ProgressBar
    private lateinit var preferences: SharedPreferences

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        preferences = getSharedPreferences("laundry_mobile_prefs", MODE_PRIVATE)

        webView = findViewById(R.id.webView)
        edtUrl = findViewById(R.id.edtUrl)
        btnLoad = findViewById(R.id.btnLoad)
        progressBar = findViewById(R.id.progressBar)

        val savedUrl = preferences.getString(KEY_SERVER_URL, DEFAULT_URL) ?: DEFAULT_URL
        edtUrl.setText(savedUrl)

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            loadWithOverviewMode = true
            useWideViewPort = true
            builtInZoomControls = false
            displayZoomControls = false
            setSupportZoom(true)
        }

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                return false
            }

            override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                progressBar.visibility = View.VISIBLE
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                progressBar.visibility = View.GONE
            }
        }

        btnLoad.setOnClickListener {
            val input = edtUrl.text.toString().trim()
            if (input.isNotBlank()) {
                val normalized = normalizeUrl(input)
                edtUrl.setText(normalized)
                preferences.edit().putString(KEY_SERVER_URL, normalized).apply()
                webView.loadUrl(normalized)
            }
        }

        if (savedInstanceState == null) {
            webView.loadUrl(savedUrl)
        }
    }

    override fun onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }

    private fun normalizeUrl(input: String): String {
        val lowered = input.lowercase()
        return if (lowered.startsWith("http://") || lowered.startsWith("https://")) {
            input
        } else {
            "http://$input"
        }
    }

    companion object {
        private const val KEY_SERVER_URL = "server_url"
        private const val DEFAULT_URL = "http://192.168.1.10:5000"
    }
}
