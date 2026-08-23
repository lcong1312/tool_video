# Tool tạo project CapCut từ file SRT và folder video

Tool này đọc tổng thời lượng từ file `.srt`, chọn ngẫu nhiên các video ngang 16:9 trong một folder, cắt thành nhiều clip ngắn, rồi tạo trực tiếp một project CapCut có nhiều clip riêng biệt trên timeline.

Mục tiêu chính: vào CapCut sẽ thấy từng clip khoảng 3 giây riêng lẻ, có thể kéo, cắt, thêm hiệu ứng, thay video hoặc chỉnh từng đoạn.

## Cách chạy nhanh nhất

Chạy file:

```bat
run_gui.bat
```

Khi chạy, tool sẽ tự kiểm tra các thành phần cần thiết:

- Python.
- FFmpeg và FFprobe.
- Các thư viện Python cần dùng.

Nếu trong folder tool có sẵn thư mục `bin` chứa:

- `ffmpeg.exe`
- `ffprobe.exe`
- `ffplay.exe`

thì tool sẽ ưu tiên dùng bộ FFmpeg này. 

Tool không bắt buộc phải cài Auto Capcut Pro. Khi copy sang máy khác, chỉ cần copy cả folder tool, bao gồm file `acp_build_project.py` và thư mục `bin`.

Nếu trong folder có thư mục:

```text
vendor/auto_capcut_pro
```

thì tool sẽ ưu tiên dùng builder portable trong đó. Vì vậy khi nén hoặc copy sang máy khác, hãy copy cả thư mục `vendor` để không bị thiếu builder.

## Cách dùng giao diện

Sau khi mở giao diện:

1. Chọn `File SRT`: chọn file phụ đề `.srt`.
2. Chọn `Folder video`: chọn folder chứa video nguồn.
3. Chọn `File xuất`: có thể để mặc định. Nếu đang tạo project CapCut thì tool chủ yếu dùng project trong CapCut, không cần quan tâm nhiều file này.
4. Chọn `CapCut.exe`: nếu tool tự nhận đúng thì không cần sửa.
5. Chọn `Mỗi clip`: mặc định là `3` giây.
6. Giữ kích thước `1920 x 1080` nếu muốn video ngang 16:9 Full HD.
7. Bật `Tạo project CapCut`.
8. Bật `Mở CapCut sau khi xong` nếu muốn tool mở CapCut tự động.
9. Bấm `Tạo video`.

Sau khi chạy xong, mở CapCut sẽ thấy project mới có tên theo tên file `.srt`.

Ví dụ file SRT là:

```text
DL14.srt
```

thì project trong CapCut sẽ có tên:

```text
DL14
```

## Video được chọn như thế nào

Tool chỉ lấy video ngang đúng tỷ lệ 16:9.

Các video dọc 9:16 hoặc video không đúng tỷ lệ sẽ bị bỏ qua. Điều này giúp project tạo ra đúng khung ngang `1920 x 1080`, tránh bị lẫn video dọc trong folder Pexels.

Các định dạng video được hỗ trợ:

```text
.mp4, .mov, .mkv, .avi, .webm, .m4v
```

## Tải video từ Pexels

GUI có thêm tùy chọn `Tải từ Pexels`.

Khi bật tùy chọn này:

1. Nhập `API key` của Pexels.
2. Nhập `Từ khóa`, ví dụ `nature`, `city`, `business`, `travel`.
3. Nhập `Luồng tải`, tối đa `10`, để tải nhiều video song song.
4. Ô `Folder video` sẽ trở thành thư mục cache để lưu video Pexels đã tải.
5. Bấm `Tạo video` như bình thường.

Số video cần tải sẽ tự tính theo thời lượng file SRT:

```text
số video = làm tròn lên(thời lượng SRT / mỗi clip)
```

Ví dụ SRT dài 300 giây, mỗi clip 3 giây thì tool sẽ cố tải 100 video.

Khi tải từ Pexels, tool luôn chỉ lấy video ngang 16:9. Bạn không cần tick thêm `Chỉ lấy video 16:9`; trong chế độ Pexels tùy chọn này sẽ tự bật.

Nếu để trống từ khóa, tool sẽ tải video phổ biến từ Pexels.

Sau lần nhập đầu tiên, API key Pexels sẽ được lưu trong file:

```text
config.json
```

ở cùng thư mục tool. Lần sau mở GUI, tool sẽ tự điền lại API key từ file này. File này có chứa key riêng của bạn nên không nên đưa lên GitHub hoặc gửi cho người khác.

Tool lưu thông tin nguồn Pexels tại:

```text
pexels_attribution.json
```

trong thư mục cache video. File này dùng để biết video lấy từ đâu và ai là tác giả trên Pexels.

## Project CapCut được tạo ra như thế nào

Tool sẽ:

1. Lấy một project CapCut sạch làm mẫu.
2. Tạo folder project mới trong thư mục draft của CapCut.
3. Render các clip ngắn vào trong nội bộ project:

```text
Resources/auto_clips
```

4. Ghi timeline để CapCut mở ra thấy nhiều clip riêng biệt.
5. Đăng ký project vào danh sách project của CapCut.

Bạn không cần vào CapCut tạo dự án mới trước.

## GPU

Nếu bật `Dùng GPU`, tool sẽ thử dùng encoder GPU của FFmpeg theo thứ tự:

```text
h264_nvenc, h264_amf, h264_qsv
```

Nếu máy không hỗ trợ GPU encoder, tool sẽ tự quay về CPU bằng `libx264`.

Lưu ý: GPU chỉ tăng tốc bước render/cắt clip bằng FFmpeg. Việc CapCut mở project hay xử lý trong giao diện CapCut là phần riêng của CapCut.

## Burn subtitle

Nếu bật `Burn subtitle vào video`, tool sẽ ghép phụ đề trực tiếp vào video xuất ra.

Nếu mục tiêu là chỉnh từng đoạn trong CapCut thì thường nên tắt mục này, vì project CapCut sẽ chứa các clip riêng lẻ để chỉnh sửa.

## Tiếp tục khi bị lỗi

Mặc định GUI bật `Tiếp tục clip đã tạo`.

Khi bật mục này, tool sẽ lưu tạm các clip đã render trong project tạm của CapCut. Nếu đang chạy mà bị lỗi hoặc phải dừng giữa chừng, chỉ cần chạy lại với cùng file SRT và cùng cấu hình, tool sẽ tự bỏ qua các clip đã tạo hợp lệ và chỉ render tiếp phần còn thiếu.

Nếu bạn đổi file SRT, đổi folder video, đổi thời lượng mỗi clip hoặc đổi kích thước video, tool sẽ tự xóa clip tạm cũ và tạo lại từ đầu để tránh dùng nhầm dữ liệu.

## Chạy bằng dòng lệnh

Tạo một video MP4 hoàn chỉnh từ SRT và folder video:

```powershell
python .\make_capcut_video.py D:\CV\DL17\voice\dl17.srt C:\Users\Admin\Videos\Pexels -o .\output.mp4
```

Tắt GPU:

```powershell
python .\make_capcut_video.py .\subtitle.srt .\videos -o .\output.mp4 --no-gpu
```

Burn phụ đề trực tiếp vào video:

```powershell
python .\make_capcut_video.py .\subtitle.srt .\videos -o .\output.mp4 --burn-subtitles
```

Giữ kết quả random giống nhau mỗi lần chạy:

```powershell
python .\make_capcut_video.py .\subtitle.srt .\videos -o .\output.mp4 --seed 123
```

## Lưu ý khi dùng

- Nên đóng các project CapCut đang mở trước khi tạo project mới.
- Nếu project cũ tạo lỗi, hãy xóa project đó trong CapCut rồi tạo lại bằng bản tool mới.
- Không nên đổi tên hoặc di chuyển folder project trong `com.lveditor.draft` bằng tay.
- Nếu copy tool sang máy khác, hãy copy cả thư mục `bin` để FFmpeg đi kèm và thư mục `vendor` để builder CapCut đi kèm.
- Máy đích cần cài CapCut. Nếu máy đó chưa từng có project CapCut nào, hãy mở CapCut, bấm `Tạo dự án` một lần,rồi kéo 1 video bất kỳ và 1 đoạn .srt bất kỳ sau đó đóng tab edit rồi chạy lại tool để tool lấy schema project mẫu.
- Folder video có thể chứa cả video ngang và dọc, tool sẽ tự lọc chỉ lấy video ngang 16:9.

## Khi gặp lỗi

Nếu báo thiếu FFmpeg:

1. Kiểm tra thư mục `bin` có `ffmpeg.exe` và `ffprobe.exe` chưa.
2. Chạy lại `run_gui.bat`.

Nếu CapCut không thấy project mới:

1. Đóng CapCut.
2. Chạy lại tool.
3. Mở CapCut lại.

Nếu CapCut báo không thể dùng dự án:

1. Xóa project lỗi trong CapCut.
2. Đảm bảo đã dùng bản tool mới.
3. Tạo lại project từ giao diện.

## GitHub source vs full setup build

Repo GitHub chi commit source code va cac script build. Cac thu muc runtime lon nhu
`bin/`, `vendor/`, `dist/`, `installer_output/` khong commit truc tiep vi GitHub
chan file tren 100MB va `vendor/VOICEVOX` co nhieu file rat lon.

De clone sang may khac va build ra setup day du:

1. Clone repo.
2. Copy lai `vendor/VOICEVOX` va `vendor/auto_capcut_pro` tu may build goc, hoac tai tu goi Release/dependencies rieng neu da upload.
3. Chay `build_setup.bat`. Script se tu tai/copy FFmpeg vao `bin/` neu thieu.
4. File setup se nam tai `installer_output/CapCutVideoToolSetup.exe`.

Neu muon dua ca `vendor` len GitHub, can dung Git LFS hoac GitHub Releases. Khong
nen commit truc tiep bang Git thuong vi cac file lon se bi GitHub tu choi khi push.
