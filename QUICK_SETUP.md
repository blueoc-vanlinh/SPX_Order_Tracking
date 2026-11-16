# Dùng app trên máy Windows mới

1. Giải nén toàn bộ `SPX_Order_Tracking_Windows.zip`, mở `SPX_Order_Tracking.exe`.
   Giữ thư mục `_internal` cạnh EXE. Máy cần Chrome và mạng truy cập SPX/Google.
2. Màn hình **Thiết lập nhanh** tự mở. Dán link Google Sheet bạn có quyền sửa.
   Để trống tên tab để dùng tab gid=0, hoặc nhập tên tab mong muốn.
3. Bấm **Kết nối Google**, chọn tài khoản và cấp quyền Google Sheets trong
   trình duyệt. App tự lưu token trên máy này và kiểm tra Sheet.
4. Bấm **Đăng nhập SPX**, đăng nhập trong Chrome của tool, chọn Hung Yen SOC,
   rồi bấm **✓** trên thanh tool để lưu và xác minh API.
5. Đóng màn hình thiết lập, bấm **▶**. Tool lấy total, tự thêm header nếu thiếu
   và ghi dữ liệu lên Sheet. Không cần tạo mẫu bằng tay.

Vào **⋯ → Thiết lập nhanh…** để đổi tài khoản Google hoặc link Sheet.
Nếu có sẵn JSON Service Account, có thể chọn **Nhập JSON Google có sẵn** thay
cho đăng nhập; file được copy riêng vào vùng dữ liệu của người dùng.

Dữ liệu cài đặt, token, phiên SPX và kết quả nằm tại
`%LOCALAPPDATA%\SPX_Order_Tracking`, tách khỏi thư mục EXE. Cập nhật bằng cách
giải nén bản app mới không làm mất thiết lập. Mỗi người/máy đăng nhập riêng;
không cần chia sẻ `service_account.json`, `token.json` hay cookie SPX.

## Dành cho người phát hành app lên GitHub

Đưa mã nguồn lên repository; file bí mật và dữ liệu cục bộ đã được bỏ qua bằng
`.gitignore`. Đưa ZIP sạch trong `release` lên **GitHub Releases** để người dùng
tải. Không upload cả thư mục làm việc đang có `.auth` và dữ liệu cá nhân.

Đăng nhập Google cần cấu hình **OAuth client loại Desktop app** dùng chung
cho ứng dụng. Đây là cấu hình ứng dụng, không phải tài khoản hay token của
người sử dụng. Trên máy build, đặt file tại `assets/google_oauth_client.json`
(được gitignore), hoặc đặt biến `SPX_GOOGLE_OAUTH_CLIENT_FILE`. Script build
chỉ đưa `client_id`/`client_secret` của OAuth Desktop vào bản phát hành, không
đưa khóa Service Account, refresh token hay phiên đăng nhập cá nhân vào đó.

Build bằng `python scripts/build_release.py` sau khi cài `requirements.txt`.
Kết quả: `release/SPX_Order_Tracking_Windows.zip`.
GitHub Actions có thể dùng secret `GOOGLE_OAUTH_CLIENT_JSON` để build tự động;
secret này chỉ là OAuth Desktop client, không dùng token cá nhân.

Trong Google Cloud của ứng dụng, bật Google Sheets API và cấu hình đối tượng
được phép đăng nhập. Nếu ứng dụng OAuth còn ở Testing, Google chỉ cho các
tài khoản trong danh sách test users truy cập. Nếu muốn cho người khác dùng,
người quản lý Google Cloud cần cấu hình/publish ứng dụng phù hợp. Đây là cấu
hình một lần của bên phát hành, không thể thay thế chỉ bằng code EXE.

Nguồn Google: [OAuth Desktop](https://developers.google.com/identity/protocols/oauth2/native-app),
[trạng thái ứng dụng OAuth](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview).

Nếu Google Workspace chặn quyền hoặc tài khoản không có quyền sửa bảng,
app sẽ hiển thị lỗi. Chọn đúng tài khoản được tổ chức cho phép và cấp quyền
Editor trên bảng tính cần ghi.
