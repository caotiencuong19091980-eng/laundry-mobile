package com.huongthinh.laundrymobile

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothSocket
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.os.Build
import android.os.Bundle
import android.view.View
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.ProgressBar
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var edtUrl: EditText
    private lateinit var btnLoad: Button
    private lateinit var btnPrinter: Button
    private lateinit var progressBar: ProgressBar
    private lateinit var preferences: SharedPreferences
    private var pendingPrintPayload: String? = null
    private var pendingAction: String = ACTION_NONE

    private val bluetoothAdapter: BluetoothAdapter? by lazy { BluetoothAdapter.getDefaultAdapter() }

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { results ->
        val denied = results.entries.any { !it.value }
        if (denied) {
            toast("Thiếu quyền Bluetooth để in hóa đơn.")
            pendingPrintPayload = null
            pendingAction = ACTION_NONE
        } else {
            when (pendingAction) {
                ACTION_CONFIGURE -> showPrinterPicker()
                ACTION_PRINT -> {
                    val payload = pendingPrintPayload
                    pendingPrintPayload = null
                    pendingAction = ACTION_NONE
                    if (!payload.isNullOrBlank()) {
                        this@MainActivity.printEscPos(payload)
                    }
                }
                else -> {
                    pendingPrintPayload = null
                    pendingAction = ACTION_NONE
                }
            }
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        preferences = getSharedPreferences("laundry_mobile_prefs", MODE_PRIVATE)

        webView = findViewById(R.id.webView)
        edtUrl = findViewById(R.id.edtUrl)
        btnLoad = findViewById(R.id.btnLoad)
        btnPrinter = findViewById(R.id.btnPrinter)
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

        webView.addJavascriptInterface(AndroidEscPosBridge(), "AndroidEscPos")

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

        btnPrinter.setOnClickListener { startConfigurePrinter() }

        if (savedInstanceState == null) {
            webView.loadUrl(savedUrl)
        }
    }

    @Deprecated("Deprecated in Java")
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

    private fun startConfigurePrinter() {
        pendingAction = ACTION_CONFIGURE
        pendingPrintPayload = null
        requestBluetoothPermissionsIfNeeded()
    }

    private fun requestBluetoothPermissionsIfNeeded() {
        val required = mutableListOf<String>()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) {
                required.add(Manifest.permission.BLUETOOTH_CONNECT)
            }
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_SCAN) != PackageManager.PERMISSION_GRANTED) {
                required.add(Manifest.permission.BLUETOOTH_SCAN)
            }
        }

        if (required.isEmpty()) {
            if (pendingAction == ACTION_CONFIGURE) {
                showPrinterPicker()
            } else if (pendingAction == ACTION_PRINT) {
                val payload = pendingPrintPayload
                pendingPrintPayload = null
                pendingAction = ACTION_NONE
                if (!payload.isNullOrBlank()) {
                    this@MainActivity.printEscPos(payload)
                }
            }
        } else {
            permissionLauncher.launch(required.toTypedArray())
        }
    }

    private fun showPrinterPicker() {
        val adapter = bluetoothAdapter
        if (adapter == null) {
            toast("Thiết bị không hỗ trợ Bluetooth.")
            return
        }

        if (!adapter.isEnabled) {
            toast("Hãy bật Bluetooth trước khi chọn máy in.")
            return
        }

        val devices = adapter.bondedDevices
            ?.filter { it.name?.isNotBlank() == true }
            ?.sortedBy { it.name }
            .orEmpty()

        if (devices.isEmpty()) {
            toast("Không có máy in đã ghép đôi. Hãy pair máy in trong cài đặt Bluetooth trước.")
            return
        }

        val labels = devices.map { "${it.name} (${it.address})" }.toTypedArray()
        AlertDialog.Builder(this)
            .setTitle("Chọn máy in Bluetooth")
            .setItems(labels) { _, which ->
                val device = devices[which]
                preferences.edit().putString(KEY_PRINTER_MAC, device.address).apply()
                toast("Đã chọn máy in: ${device.name}")
            }
            .setNegativeButton("Hủy", null)
            .show()
    }

    private fun printEscPos(payloadJson: String) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val hasConnectPermission = ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.BLUETOOTH_CONNECT
            ) == PackageManager.PERMISSION_GRANTED
            val hasScanPermission = ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.BLUETOOTH_SCAN
            ) == PackageManager.PERMISSION_GRANTED
            if (!hasConnectPermission || !hasScanPermission) {
                pendingAction = ACTION_PRINT
                pendingPrintPayload = payloadJson
                requestBluetoothPermissionsIfNeeded()
                return
            }
        }

        val adapter = bluetoothAdapter
        if (adapter == null) {
            toast("Thiết bị không hỗ trợ Bluetooth.")
            return
        }
        if (!adapter.isEnabled) {
            toast("Bluetooth chưa bật.")
            return
        }

        val printerMac = preferences.getString(KEY_PRINTER_MAC, null)
        if (printerMac.isNullOrBlank()) {
            runOnUiThread {
                toast("Chưa chọn máy in. Vui lòng bấm nút Máy in BT để chọn máy in trước.")
            }
            return
        }

        val device = try {
            adapter.getRemoteDevice(printerMac)
        } catch (_: IllegalArgumentException) {
            runOnUiThread { toast("Địa chỉ máy in không hợp lệ. Vui lòng chọn lại máy in.") }
            return
        }

        Thread {
            var socket: BluetoothSocket? = null
            try {
                adapter.cancelDiscovery()
                socket = device.createRfcommSocketToServiceRecord(SPP_UUID)
                socket.connect()
                val output = socket.outputStream
                val data = buildEscPosBytes(payloadJson)
                output.write(data)
                output.flush()
                runOnUiThread { toast("Đã gửi lệnh in ESC/POS thành công.") }
            } catch (e: Exception) {
                runOnUiThread { toast("In thất bại: ${e.message ?: "không xác định"}") }
            } finally {
                try {
                    socket?.close()
                } catch (_: Exception) {
                }
            }
        }.start()
    }

    private fun buildEscPosBytes(payloadJson: String): ByteArray {
        val payload = JSONObject(payloadJson)
        val builder = StringBuilder()

        val shopName = payload.optString("shopName", "GIAT LA HUONG THINH CO SO 1")
        val orderId = payload.optString("orderId", "")
        val customer = payload.optString("customer", "")
        val phone = payload.optString("phone", "")
        val service = payload.optString("service", "")
        val total = payload.optString("total", "")
        val paid = payload.optString("paid", "")
        val debt = payload.optString("debt", "")
        val status = payload.optString("status", "")
        val time = payload.optString("time", "")

        builder.append(center(shopName, 32)).append('\n')
        builder.append(center("HOA DON GIAT LA", 32)).append('\n')
        builder.append("--------------------------------\n")
        if (orderId.isNotBlank()) builder.append("Ma don: #").append(orderId).append('\n')
        if (customer.isNotBlank()) builder.append("Khach: ").append(customer).append('\n')
        if (phone.isNotBlank()) builder.append("SDT: ").append(phone).append('\n')
        if (service.isNotBlank()) builder.append("DV: ").append(service).append('\n')
        if (total.isNotBlank()) builder.append("Tong: ").append(total).append('\n')
        if (paid.isNotBlank()) builder.append("Da tra: ").append(paid).append('\n')
        if (debt.isNotBlank()) builder.append("Con no: ").append(debt).append('\n')
        if (status.isNotBlank()) builder.append("Trang thai: ").append(status).append('\n')
        if (time.isNotBlank()) builder.append("In luc: ").append(time).append('\n')

        val items: JSONArray? = payload.optJSONArray("lines")
        if (items != null && items.length() > 0) {
            builder.append("--------------------------------\n")
            for (i in 0 until items.length()) {
                val line = items.optString(i, "")
                if (line.isNotBlank()) {
                    builder.append(line).append('\n')
                }
            }
        }

        builder.append("--------------------------------\n")
        builder.append(center("Cam on quy khach!", 32)).append('\n')
        builder.append(center("A software program authored by Cuongct", 32)).append('\n')

        val escPos = mutableListOf<Byte>()
        escPos.addAll(byteArrayOf(0x1B, 0x40).toList())
        escPos.addAll(byteArrayOf(0x1B, 0x61, 0x00).toList())
        escPos.addAll(toPrintableAscii(builder.toString()).toList())
        escPos.addAll(byteArrayOf(0x0A, 0x0A, 0x0A).toList())
        escPos.addAll(byteArrayOf(0x1D, 0x56, 0x41, 0x03).toList())
        return escPos.toByteArray()
    }

    private fun toPrintableAscii(text: String): ByteArray {
        val normalized = text
            .replace("đ", "d")
            .replace("Đ", "D")
        return normalized.toByteArray(Charsets.US_ASCII)
    }

    private fun center(text: String, width: Int): String {
        if (text.length >= width) return text.take(width)
        val padding = (width - text.length) / 2
        return " ".repeat(padding) + text
    }

    private fun toast(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
    }

    inner class AndroidEscPosBridge {
        @JavascriptInterface
        fun printEscPos(payload: String) {
            this@MainActivity.printEscPos(payload)
        }

        @JavascriptInterface
        fun configurePrinter() {
            runOnUiThread { startConfigurePrinter() }
        }
    }

    companion object {
        private const val KEY_SERVER_URL = "server_url"
        private const val KEY_PRINTER_MAC = "printer_mac"
        private const val DEFAULT_URL = "http://192.168.1.10:5000"
        private const val ACTION_NONE = "none"
        private const val ACTION_CONFIGURE = "configure"
        private const val ACTION_PRINT = "print"
        private val SPP_UUID: UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
    }
}
