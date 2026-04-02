# Phần mềm quản lý giặt là (Python)

Ứng dụng hiện có 2 bản:

- Bản desktop: `app.py` (Tkinter)
- Bản web mobile/tablet: `web_app.py` (Flask) dùng được trên iPad/điện thoại

## Bản web cho iPad/điện thoại

### 1) Cài thư viện

```bash
python -m pip install -r requirements.txt
```

### 2) Chạy server

```bash
python web_app.py
```

Server mặc định chạy tại:

- `http://127.0.0.1:5000` (trên máy tính)

### 3) Mở trên điện thoại/iPad trong cùng Wi-Fi

- Trên máy tính, lấy IP LAN bằng lệnh `ipconfig` (ví dụ `192.168.1.10`)
- Trên điện thoại/iPad mở trình duyệt:
  - `http://192.168.1.10:5000`

## Cài như app trên iPhone (PWA)

Với bản cloud Railway (`https://...up.railway.app`):

1. Mở URL trên Safari iPhone
2. Bấm nút `Share`
3. Chọn `Add to Home Screen`
4. Mở icon ngoài màn hình để dùng như app (standalone)

## Chức năng bản web

- Tạo đơn mới
- Tìm kiếm theo mã đơn/tên/SĐT/trạng thái/dịch vụ
- Tìm nợ: nhập `nợ`, `khách nợ`, hoặc `tên + nợ`
- Cập nhật trạng thái và thanh toán
- Mở hóa đơn in (khổ 57x30mm) + nút in

## Dữ liệu

- Database dùng chung: `laundry.db`
- QR thanh toán: `payment_qr.png`
