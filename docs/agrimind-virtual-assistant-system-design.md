# System Design — AgriMind Virtual Assistant v1

## Mục tiêu

AgriMind chuyển từ hệ thống hỏi đáp sang trợ lý nông nghiệp cá nhân hóa cho một nông trại mỗi tài khoản. Trợ lý hiểu hội thoại đa lượt, dùng RAG và dự báo thời tiết, đề xuất việc hoặc nhật ký và chỉ ghi dữ liệu sau xác nhận.

## Kiến trúc

Flutter giao tiếp FastAPI qua SSE `POST /api/v1/chat/stream`. FastAPI chạy LangGraph gồm planner, guardrail, retrieval, generation, reflection, memory write, action proposal và memory extraction. PostgreSQL lưu lịch sử, hồ sơ nông trại, task, log, action chờ xác nhận, device token và notification. Redis phục vụ cache; Qdrant phục vụ RAG; worker định kỳ tạo in-app notification và gửi FCM khi có credentials.

## Luồng chính

1. API xác thực Supabase JWT, lưu message người dùng và nạp tám lượt gần nhất.
2. LangGraph tư vấn bằng hồ sơ nông trại, history, RAG và thời tiết; token low/medium-risk được stream qua SSE.
3. Yêu cầu “nhắc tôi” hoặc “ghi nhật ký” tạo `PendingAction` hết hạn sau 15 phút, trả về metadata SSE.
4. Flutter hiển thị thẻ xác nhận. `POST /assistant/actions/{id}/confirm` kiểm tra ownership và chỉ sau đó tạo task/log; cancel chỉ đổi trạng thái action.
5. Worker quét task đến hạn và mưa xác suất từ 70%, ghi notification theo dedupe key; FCM là lớp gửi thêm, không ảnh hưởng notification trong app.

## API

- `GET|PUT /api/v1/assistant/farm-profile`
- `GET /api/v1/assistant/tasks`, `GET /api/v1/assistant/notifications`
- `POST|DELETE /api/v1/assistant/device-tokens`
- `POST /api/v1/assistant/actions/{id}/confirm|cancel`

## Bảo mật và vận hành

Tất cả dữ liệu assistant gắn `user_id`; action ID được kiểm tra ownership, pending status và thời hạn. Prompt injection bị chặn trước DB/model. Firebase credentials chỉ đọc từ biến môi trường/volume, không commit. Worker chạy tách backend qua Docker Compose và retry ở chu kỳ sau khi external weather/FCM lỗi.

## Rollout và kiểm thử

Chạy migration Alembic trước deploy, cấu hình Firebase nếu cần push, rồi triển khai backend và worker. Theo dõi cache hit, action confirmation rate, notification delivery và tỷ lệ cảnh báo trùng. Kiểm thử history đa lượt, ownership, action hết hạn, task due, weather dedupe và UI confirm/cancel.
