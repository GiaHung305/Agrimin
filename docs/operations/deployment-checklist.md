# Checklist triển khai AgriMind

## Phạm vi hiện tại

`compose.yaml` là cấu hình chạy local/pilot trên một máy. File này vẫn
mount source backend, công khai cổng PostgreSQL, Redis và Qdrant trên host, đồng
thời dùng mật khẩu database dành cho development. Không dùng nguyên trạng trên
máy chủ Internet.

## Cổng bắt buộc trước deploy

1. Tạo cấu hình production riêng, không mount source code và không công khai
   PostgreSQL, Redis hoặc Qdrant ra Internet.
2. Đặt `ENVIRONMENT=production` và khai báo chính xác domain HTTPS trong
   `CORS_ORIGINS`. Không dùng `*` cùng credential.
3. Cấp secret qua môi trường của nền tảng triển khai; không sao chép
   `backend/.env`, Firebase Admin JSON hoặc key provider vào image/Git.
4. Cấu hình `ADMIN_USER_IDS` hoặc `ADMIN_EMAILS`, rồi kiểm tra bằng một user
   thường và một admin thật.
5. Sao lưu PostgreSQL và Qdrant trước migration hoặc nâng image. Thử restore
   trên môi trường staging trước khi gọi là có disaster recovery.
6. Chạy `alembic upgrade head`, kiểm tra API health, worker health, một lượt chat
   SSE, retrieval và một notification đến hạn.
7. Cấu hình GitHub Environment `production` theo tài liệu CI/CD, chạy quality và
   release workflow thử; xác nhận Web dùng đúng HTTPS API, APK được ký bằng
   release keystore, Firebase package khớp application ID và có thể rollback về
   tag trước.
8. Soak worker ít nhất 24 giờ, không có reminder trùng, heartbeat mất hoặc
   delivery retry bị kẹt.

## Phiên bản đã pin

- Qdrant được pin ở `v1.18.3` thay cho `latest` để tránh tự đổi storage engine
  ngoài release window. Chỉ nâng từng minor version sau khi đã backup và kiểm
  tra hướng dẫn upgrade chính thức.
- Flutter dùng `geolocator 14.0.3`, `package_info_plus 10.2.1` gián tiếp,
  `flutter_secure_storage 10.3.1` và `file_picker 12.0.0`. Các bản này xử lý
  cảnh báo Built-in Kotlin và cho phép Web/Wasm dry run.

## Kiểm tra local tương ứng

```powershell
cd frontend_flutter
flutter analyze lib
flutter test
flutter build web --release
flutter build apk --debug

cd ..
docker compose -f compose.yaml -f compose.gpu.yaml config --quiet
docker compose exec backend alembic upgrade head
docker compose exec backend pytest -q
```
