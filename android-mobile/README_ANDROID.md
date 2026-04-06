# Android APK (Xiaomi)

Project Android nằm ở thư mục: `android-mobile`

## Build APK trong Android Studio

1. Mở Android Studio
2. `Open` -> chọn thư mục `android-mobile`
3. Chờ `Gradle Sync` hoàn tất
4. Chọn `Build` -> `Build Bundle(s) / APK(s)` -> `Build APK(s)`
5. APK nằm ở:
   - `android-mobile/app/build/outputs/apk/debug/app-debug.apk`

## Cài trên Xiaomi

1. Bật `USB debugging` trên điện thoại
2. Cắm cáp USB và cho phép debug
3. Cài APK bằng kéo-thả hoặc dùng:
   - `adb install -r app-debug.apk`

## Lưu ý dùng app

- App mở bằng WebView URL server nội bộ.
- URL mặc định: `http://192.168.1.10:5000`
- Đổi URL ngay trên app nếu IP máy tính của bạn khác.
- Máy tính phải chạy web server `python web_app.py` cùng Wi-Fi với điện thoại.

## In nhiệt ESC/POS Bluetooth trực tiếp

1. Pair máy in nhiệt Bluetooth trong phần cài đặt Bluetooth của điện thoại trước.
2. Mở app, bấm nút `Máy in BT` để chọn máy in đã pair.
3. Mở trang hóa đơn (`In đơn`) trong app.
4. Bấm nút `In Bluetooth ESC/POS` trên trang hóa đơn.

Ghi chú:
- In trực tiếp ESC/POS, không đi qua hộp thoại in của Android.
- Nội dung in dùng font ASCII (không dấu) để tương thích phần lớn máy in ESC/POS phổ thông.
