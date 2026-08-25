# Auth, session và phân quyền

## Luồng phiên đăng nhập

Flutter đăng nhập/đăng ký qua Supabase Auth và lưu access token, refresh token,
thời điểm hết hạn trong secure storage. Trước khi gọi API, app tự refresh nếu
token sắp hết hạn. Khi mở app, `GET /api/v1/auth/session` xác thực JWT và trả về
role/permission do backend quyết định.

Luồng khôi phục mật khẩu dùng Supabase recovery email. App đọc recovery session
từ query/fragment của redirect, yêu cầu người dùng đặt mật khẩu mới rồi thu hồi
session recovery. Ngay sau khi lưu session, Web dùng `history.replaceState` để
xóa query/fragment chứa token khỏi thanh địa chỉ mà không reload trang.
`AUTH_REDIRECT_URL` được truyền bằng Flutter `--dart-define` ở môi trường deploy;
khi phát triển Web, app dùng URL hiện tại đã bỏ query/fragment. Màn hình xác minh
email có nút gửi lại qua endpoint Supabase `resend`.

Không suy luận quyền từ metadata do người dùng nhập và không hardcode email
Admin trong Flutter. Backend xác minh `aud`, `iss`, chữ ký và thời hạn JWT bằng
JWKS của Supabase; JWKS có cache TTL và tự refresh khi khóa được xoay.

## Role và permission hiện có

| Role | Permission |
|---|---|
| `user` | `assistant:use`, `farm:manage` |
| `admin` | Toàn bộ permission trên, `document:manage`, `operations:view` |

Kho tài liệu là corpus dùng chung. Chỉ tài khoản có `document:manage` mới thấy
menu quản trị trong Flutter và mới gọi được API upload, phân loại, deactivate,
purge. Backend vẫn là lớp thực thi quyền cuối cùng.

`operations:view` mở dashboard worker và lịch sử gửi notification. API không
trả device token, nội dung credential hoặc user ID; user thường không thấy menu
và gọi trực tiếp vẫn nhận `403`.

## Cấu hình Admin

Trong `backend/.env`, cấu hình một hoặc cả hai biến dạng danh sách phân tách bởi
dấu phẩy:

```dotenv
ADMIN_USER_IDS=<supabase-user-uuid>
ADMIN_EMAILS=admin@example.com
```

Nếu cả hai để trống thì không có tài khoản nào là Admin, kể cả development.
Sau khi đổi cấu hình, restart backend. Không đưa service-role key hay JWT của
người dùng vào Git.

## Logout và thiết bị

Khi logout, Flutter thu hồi FCM device token của đúng user trước, xóa session
cục bộ và thực hiện remote logout theo kiểu best effort. Nếu mạng lỗi, local
logout vẫn hoàn tất để người dùng không bị kẹt trong ứng dụng.

OAuth chưa bật mặc định. Chỉ thêm Google/Apple sau khi provider, callback URL,
deep-link Android/iOS và chính sách liên kết tài khoản đã được cấu hình trong
Supabase; không chỉ thêm một nút UI khi callback chưa sẵn sàng.
