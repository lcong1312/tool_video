# CapCut Video Tool Update Server

Project này có thể dùng Cloudflare Tunnel làm server update tĩnh.

## Luồng hoạt động

1. App đang cài trên máy khách đọc `latest.json`.
2. Nếu `version` trong manifest lớn hơn `APP_VERSION` trong app, GUI sẽ hiện thông báo.
3. Khi người dùng bấm `Yes`, app tải `CapCutVideoToolSetup.exe` vào thư mục đang cài app.
4. Tải xong, app hỏi chạy installer mới để cập nhật.

## Thiết lập máy server

Sau khi build xong:

```powershell
python .\tools\make_update_manifest.py --version 1.0.1 --notes "Mô tả bản cập nhật"
```

Lệnh này sẽ copy installer từ `installer_output\CapCutVideoToolSetup.exe` sang `updates\` và tạo `updates\latest.json`.

Chạy server tĩnh:

```bat
tools\serve_updates.bat
```

Hoặc chạy ẩn nền, không hiện cửa sổ CMD:

```bat
tools\start_update_server_hidden.bat
```

Tắt server chạy nền:

```bat
tools\stop_update_server.bat
```

App đã fix cứng URL update mặc định:

```text
https://update.nexflow.click/latest.json
```

Nếu muốn dùng đúng URL này, server/tunnel cần phục vụ được file `latest.json` và `CapCutVideoToolSetup.exe` qua HTTP ở domain/port đó.

Cloudflare Tunnel trỏ vào:

```text
http://localhost:18080
```

URL manifest công khai hiện dùng:

```text
https://update.nexflow.click/latest.json
```

## Thiết lập máy khách

Máy khách không cần nhập gì thêm nếu dùng URL mặc định đã fix cứng.

Nếu sau này đổi domain, mở app, vào tab `Setting`, nhập `Manifest URL`, bấm `Lưu`, rồi bấm `Kiểm tra`.

Cũng có thể cấu hình bằng biến môi trường:

```env
CAPCUT_VIDEO_TOOL_UPDATE_URL=https://update.nexflow.click/latest.json
```

## Mỗi lần ra bản mới

Chạy một lệnh:

```bat
tools\release_update.bat X.Y.Z "Nội dung thay đổi"
```

Lệnh này sẽ tự:

1. Set version trong source và installer.
2. Build lại app/setup.
3. Tạo `updates\latest.json` đúng version.

Đảm bảo Cloudflare Tunnel/server update vẫn đang chạy.
