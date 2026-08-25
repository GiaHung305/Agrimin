# Vận hành assistant worker

## Trạng thái và dashboard

Worker ghi heartbeat có TTL vào Redis cho ba chu kỳ: nhắc công việc, theo dõi
nông trại và gửi push. Endpoint công khai `/api/v1/health/worker` chỉ trả trạng
thái kỹ thuật. Dashboard chi tiết `/api/v1/operations/worker-dashboard` yêu cầu
quyền `operations:view` và được hiển thị trong menu Admin của Flutter.

Dashboard tự làm mới mỗi 15 giây, gồm:

- tuổi heartbeat và số lỗi liên tiếp của từng chu kỳ;
- tổng notification theo trạng thái pending/retry/delivered/failed/cancelled;
- 30 lần gửi gần nhất và mã lỗi đã chuẩn hóa;
- lỗi chu kỳ worker trong 7 ngày gần nhất.

Không hiển thị FCM token, credential hoặc response body từ provider.

Hạn công việc và lịch theo dõi được so sánh theo `Asia/Ho_Chi_Minh`. Timestamp
vận hành của outbox (`next_attempt_at`, lần thử, gửi thành công) được lưu UTC và
API trả ISO-8601 có timezone; migration `l2b84c4d15e9` chuẩn hóa dữ liệu cũ từng
được ghi bằng đồng hồ local.

## Retry, dead-letter và lịch sử

`notification_deliveries` là outbox hiện tại. Mỗi lần thử được ghi vào
`notification_delivery_attempts`. Retry dùng exponential delay và tối đa 5 lần;
sau đó delivery chuyển `failed`, đóng vai trò dead-letter để Admin điều tra.
Không tự phát lại dead-letter vì có thể tạo thông báo cũ ngoài ý muốn.

Lỗi cấp chu kỳ được ghi vào `worker_failures` bằng error class đã rút gọn, không
lưu exception message có thể chứa dữ liệu nhạy cảm.

## Chống chạy trùng

Mỗi chu kỳ giữ một PostgreSQL advisory lock riêng trong thời gian thực thi.
Replica không lấy được lock sẽ bỏ qua lượt đó. Các truy vấn due-work vẫn dùng
`FOR UPDATE SKIP LOCKED`, còn notification dùng `dedupe_key` duy nhất; ba lớp
này bảo vệ khi tăng số worker mà không cần thêm message broker trong V1.

Sau khi áp dụng thay đổi, chạy:

```powershell
docker compose exec backend alembic upgrade head
docker compose up -d --build backend assistant-worker
```
