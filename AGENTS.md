# Hướng dẫn làm việc trong repository AgriMind

## Phạm vi

File này áp dụng cho toàn bộ repository. Nếu một thư mục con có `AGENTS.md`
riêng, file gần mã nguồn đang sửa hơn được ưu tiên cho thư mục đó.

Skill `manage-agrimind` là công cụ cá nhân nằm ngoài repository. Không sao chép
Skill, `SKILL.md`, `agents/openai.yaml`, `references/` hoặc asset của Skill vào
source, Docker image hay artefact phát hành của AgriMind.

## Kiến trúc cần giữ

- `backend/`: FastAPI, LangGraph, PostgreSQL, Redis, Qdrant, guardrail và worker.
- `embedding-service/`: dịch vụ embedding/reranking độc lập; có thể chạy GPU qua
  `compose.gpu.yaml`.
- `backend/mcp_servers/`: MCP server thời tiết.
- `frontend_flutter/`: ứng dụng giao diện chính cho người dùng khi triển khai.
- `docs/`: tài liệu kiến trúc và vận hành.

Luồng chat production duy nhất là Flutter gọi
`POST /api/v1/chat/stream` qua SSE. Không tạo thêm CLI chat, endpoint chat song
song hoặc workflow khác có thể làm hành vi giữa development và deployment lệch
nhau. Script chẩn đoán chỉ được gọi lại chính API/workflow production và không
được trở thành luồng sản phẩm thứ hai.

## Quy tắc backend và AI

- Mọi API dữ liệu người dùng phải dùng auth hiện tại và lọc theo `user_id`.
  Không truy vấn task, nhật ký, hồ sơ, action, token thiết bị hoặc notification
  chỉ bằng ID mà thiếu ownership check.
- Mọi hành động làm thay đổi dữ liệu do trợ lý đề xuất phải tạo pending action,
  có thời hạn và chỉ thực thi sau khi đúng người dùng xác nhận. Hủy hoặc action
  hết hạn không được tạo dữ liệu.
- Confidence phải được tính động bằng logic tập trung trong
  `backend/app/workflow/confidence.py`; không hardcode một giá trị như `0.8`.
- Kiểm tra prompt injection phải diễn ra trước khi nội dung không tin cậy đi vào
  workflow. Không vô hiệu hóa `security_checks` để làm test hoặc demo chạy qua.
- Giữ Postgres checkpointer cho hội thoại đa lượt. `thread_id` phải ổn định theo
  conversation và được cô lập giữa người dùng.
- Nội dung rủi ro cao chỉ được phát cho client sau guardrail. Tư vấn thông thường
  có thể streaming token.
- Lỗi Redis, cache hoặc nguồn phụ nên suy giảm an toàn khi có thể; lỗi bắt buộc
  không được bị nuốt im lặng. Dùng `logging`, không dùng `print` debug.
- Không log token, API key, private key, nội dung credential hoặc response body
  có khả năng chứa dữ liệu nhạy cảm.

## Dữ liệu và migration

- Thay đổi schema SQLAlchemy phải đi cùng Alembic migration có `upgrade()` và
  `downgrade()` hợp lệ.
- Migration phải chạy được trên PostgreSQL hiện có, tránh phụ thuộc vào trạng
  thái database sạch và bổ sung index cho truy vấn theo ownership, hạn hoặc
  deduplication khi cần.
- Dùng thời gian nhất quán; worker nhắc việc hoạt động theo
  `Asia/Ho_Chi_Minh`. Luôn xử lý rõ timezone trước khi so sánh thời điểm.
- Notification phải có dedupe key hoặc cơ chế tương đương để retry không gửi
  trùng.

## Docker và cấu hình dịch vụ

- Trong container, gọi dịch vụ khác bằng tên Compose, không dùng `localhost`.
  Ví dụ: `embedding-service:8001`, `postgres:5432`, `redis:6379`,
  `qdrant:6333`, `mcp-weather-server:8002`.
- `compose.yaml` phải chạy được theo cấu hình nền. GPU được bật bằng overlay:

  ```powershell
  docker compose -f compose.yaml -f compose.gpu.yaml up -d
  ```

- RTX 3050 4 GB chỉ nên dành GPU cho embedding theo cấu hình đã kiểm chứng; không
  đưa thêm model lên GPU nếu chưa đo VRAM và kiểm thử health.
- Khi thêm biến môi trường, cập nhật file ví dụ/tài liệu phù hợp nhưng không ghi
  giá trị bí mật vào source.

## Flutter

- Flutter là giao diện production; không thêm luồng gọi chat bằng câu lệnh.
- Dùng `ApiService` làm điểm gọi backend thống nhất. Android emulator truy cập
  máy host qua `10.0.2.2`, không qua `localhost`.
- Giữ Material 3 và token màu trong `lib/design_system/theme/app_theme.dart`; tránh hardcode
  một hệ màu mới riêng lẻ ở từng màn hình.
- Điều hướng chính nằm trong `HomeShell`: Trợ lý, Công việc, Thông báo và Nông
  trại. Tránh tạo menu hoặc màn hình trùng chức năng nếu không có lý do UX rõ.
- Giữ streaming SSE cho chat và xử lý frame theo delimiter; không giả định một
  network chunk luôn là một SSE event hoàn chỉnh.
- Sau `await`, kiểm tra `mounted` trước khi dùng `context` hoặc `setState`.
  Callback của `setState` phải đồng bộ, không trả `Future`.
- Token FCM phải đăng ký/thu hồi theo đúng tài khoản. Không nhúng Firebase Admin
  credential vào ứng dụng Flutter.

## Secrets và file sinh tự động

- Không commit `backend/.env`, `backend/secrets/`, Firebase service-account JSON,
  private key, token hoặc credential tải về từ cloud console.
- `frontend_flutter/android/app/google-services.json` là cấu hình Firebase client
  dành cho Android và có thể được version control; nó không thay thế Firebase
  Admin credential ở backend.
- Không commit `.dart_tool/`, `build/`, `android/.gradle/`, `__pycache__/`, virtual
  environment, log hoặc artefact tạm.
- Nếu secret từng xuất hiện trong ảnh, log hoặc Git, yêu cầu rotate/revoke; chỉ
  xóa file khỏi commit là chưa đủ.

## Kiểm thử bắt buộc

Chạy kiểm tra phù hợp với phần đã sửa. Trước khi commit thay đổi xuyên suốt hệ
thống, tối thiểu chạy:

```powershell
docker compose -f compose.yaml -f compose.gpu.yaml exec backend pytest -q
cd frontend_flutter
flutter analyze lib
flutter build apk --debug
```

Khi sửa migration, chạy thêm:

```powershell
docker compose exec backend alembic upgrade head
```

Khi sửa Docker/network AI, kiểm tra từ chính container backend thay vì chỉ gọi
port trên host. Health container không đủ chứng minh luồng chat hoạt động; cần
kiểm tra ít nhất một lời gọi embedding/RAG hoặc chat end-to-end có liên quan.

## Tiêu chí hoàn tất

- Không phá luồng chat SSE production hoặc tách thành hai cách gọi.
- Auth/ownership, confirmation, expiry và notification deduplication vẫn đúng.
- Test liên quan pass, Flutter analyzer sạch và artefact mục tiêu build được.
- Không có secret hoặc cache build trong Git diff.
- Tài liệu/cấu hình được cập nhật khi kiến trúc hoặc cách chạy thay đổi.
- Chỉ commit/push khi người dùng yêu cầu; báo rõ commit, branch và kết quả test.
