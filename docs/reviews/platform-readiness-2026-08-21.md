# Platform readiness gate — 2026-08-21

## Quyết định

**Chưa chuyển sang phase tiếp theo.** Code đã đủ để bắt đầu giai đoạn xác minh
release, nhưng chưa có bằng chứng vận hành/remote CI đủ mạnh để mở phase mới.
Không có hạng mục nào của phase tiếp theo được triển khai trong thay đổi này.

## Phần đã đạt ở checkout hiện tại

| Trụ cột | Bằng chứng |
|---|---|
| Auth/session | Access + refresh token, refresh trước hạn, retry 401 cho chat SSE, remote/local logout và thu hồi FCM token |
| Phân quyền | Backend trả role/permission; tài liệu dùng `document:manage`; user thường không thấy menu; backend vẫn chặn gọi trực tiếp |
| Worker | Timeout mỗi cycle, backoff có giới hạn, graceful stop, heartbeat theo ba cycle và Docker healthcheck |
| Design System | Breakpoint, motion, notice, state view, responsive content và theme Material 3 mở rộng |
| CI/CD | Workflow quality cho backend/Flutter/container; release tạo image GHCR và artefact Flutter, không tự deploy production |
| Kiểm thử local | Backend 411/411; Flutter analyzer sạch; Flutter 13/13; APK debug và Web release build thành công; Compose config hợp lệ |

## Cổng còn mở trước phase tiếp theo

1. Chạy workflow quality trên GitHub và xác nhận cả ba required checks xanh;
   hiện tại mới xác minh YAML/local command, chưa có GitHub run.
2. Cấu hình ít nhất một Admin thực trong `ADMIN_USER_IDS` hoặc `ADMIN_EMAILS`,
   sau đó test thủ công bằng hai tài khoản thật: user không thấy kho tài liệu,
   Admin thao tác được và gọi trực tiếp bằng user nhận 403.
3. Chạy Docker đầy đủ và soak worker tối thiểu 24 giờ; `/api/v1/health/worker`
   phải giữ `ok`, không có heartbeat missing/failed, reminder không trùng và push
   retry chuyển trạng thái đúng.
4. Kích hoạt `release.yml` bằng workflow dispatch/tag thử; xác nhận image GHCR,
   Flutter artefact và quy trình rollback/tagging.
5. Giải quyết gate release-candidate cũ: chọn/promote đúng model fingerprint hoặc
   chạy lại gate cho champion, rollout Vision theo allowlist và theo dõi lỗi/chi
   phí. Không dùng benchmark challenger để tuyên bố production GA.
6. Theo dõi và nâng plugin gây cảnh báo Kotlin Built-in Kotlin trước khi Flutter
   biến cảnh báo này thành lỗi build. Flutter Web JS hiện build được; nếu phase
   tiếp theo yêu cầu WebAssembly thì phải thay/nâng `flutter_secure_storage_web`
   để xử lý cảnh báo tương thích Wasm.

Khi sáu cổng trên có bằng chứng đạt, có thể ra quyết định sang phase tiếp theo.
Quyết định đó vẫn cần lệnh rõ ràng của người dùng; tài liệu này không tự động mở
hoặc triển khai phase mới.
