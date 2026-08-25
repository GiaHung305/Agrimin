# CI/CD của AgriMind

## Quality gates

`.github/workflows/quality-gates.yml` chạy trên pull request vào `main` và các
nhánh phát triển được đẩy lên GitHub. Pipeline kiểm tra độc lập năm lớp:

- Backend: cài dependency từ `backend/requirements.lock`, compile module và chạy toàn bộ pytest.
- Migration: nâng PostgreSQL sạch lên head và chạy `alembic check`.
- Secret: quét toàn bộ Git history bằng Gitleaks.
- Flutter: kiểm tra format, analyze, widget/golden test, build Web release và
  Android debug APK.
- Container: validate cấu hình Compose nền + GPU và build image backend.

Không merge khi một trong các job này đỏ. Branch protection trên GitHub cần yêu
cầu năm status check tương ứng: `Backend tests`, `Migration integrity`,
`Secret scanning`, `Flutter analyze, test and build` và
`Container configuration`.

`backend/requirements.txt` là tập ràng buộc để chủ động nâng cấp dependency;
`backend/requirements.lock` là bộ phiên bản Linux/Python 3.12 đã kiểm thử mà CI
và Docker bắt buộc cài. Chỉ cập nhật lockfile sau khi build image, chạy
`pip check` và toàn bộ pytest thành công. Base Python trong Dockerfile cũng được
khóa digest để build không tự đổi nền hệ điều hành.

## Continuous delivery

`.github/workflows/release.yml` chỉ chạy khi đẩy tag `v*` hoặc được kích hoạt thủ
công. Release bắt buộc gọi lại toàn bộ quality gates trước khi publish. Sau khi
gate xanh, workflow này:

1. Build và đẩy backend/embedding image lên GitHub Container Registry (GHCR).
2. Build Flutter Web release đã trỏ đúng API HTTPS và Android release APK đã
   ký để kiểm thử phân phối.
3. Lưu artefact Flutter trong 14 ngày.

Đây là continuous delivery đến registry/artefact, chưa tự deploy production.
Việc deploy cần một môi trường đích, secret riêng và bước phê duyệt; không đặt
credential production trong repository hoặc workflow.

## Cấu hình bắt buộc

- Bật GitHub Actions và Packages cho repository.
- Bật branch protection cho `main` với năm quality gates nêu trên.
- Giữ quyền workflow mặc định ở mức read; release chỉ xin `packages: write`.
- Không thêm Supabase, Firebase Admin hay model API key vào YAML. Nếu sau này có
  deployment job, dùng GitHub Environment secrets và required reviewers.

## GitHub Environment `production`

Job tạo Flutter artefact chỉ chạy sau khi environment `production` được phê
duyệt và đủ cấu hình. Các repository/environment variables bắt buộc:

- `API_BASE_URL`: URL HTTPS kết thúc bằng `/api/v1`.
- `SUPABASE_URL` và `SUPABASE_PUBLISHABLE_KEY`: cấu hình client công khai.
- `AUTH_REDIRECT_URL`: URL HTTPS nhận callback xác minh/khôi phục mật khẩu.
- `ANDROID_APPLICATION_ID`: package Android production duy nhất, ví dụ
  `com.example.agrimind`; giá trị này phải khớp Firebase client production.

Các environment secrets bắt buộc:

- `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`,
  `ANDROID_KEY_PASSWORD`, `ANDROID_KEY_ALIAS`.
- `ANDROID_GOOGLE_SERVICES_JSON_BASE64`: nội dung `google-services.json` của
  đúng application ID production, mã hóa base64.

Workflow chỉ giải mã keystore/Firebase config trong runner tạm và xóa các file
tạm trước khi upload artefact. Thiếu cấu hình hoặc dùng URL không phải HTTPS sẽ
làm release dừng rõ ràng thay vì tạo một artefact trỏ nhầm về `localhost`.
