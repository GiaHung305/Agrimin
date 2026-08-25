# Tài liệu AgriMind

Thư mục này là điểm bắt đầu để đọc hệ thống. Tài liệu được nhóm theo mục đích,
không đặt lẫn kiến trúc, benchmark và biên bản release trong cùng một cấp.

## Bắt đầu từ đâu

1. [Tổng quan hệ thống](architecture/system-overview.md): thành phần, dữ liệu và
   các luồng nghiệp vụ từ giao diện đến AI, lưu trữ và worker.
2. [Workflow trợ lý AI](architecture/virtual-assistant-system.md): chi tiết
   LangGraph, RAG, Vision, guardrail, memory và confidence.
3. [Design system Flutter](design-system/flutter-design-system.md): token,
   component, quy tắc tổ chức feature và cách mở rộng giao diện.
4. [Release review Phase 1-4](reviews/phase-1-4-release-review.md): trạng thái
   kiểm chứng của các năng lực hiện có.
5. [CI/CD](operations/ci-cd.md): quality gates, artefact release và cấu hình
   branch protection cần thiết.
6. [Auth và phân quyền](operations/auth-and-roles.md): refresh session, role,
   permission và cách cấu hình Admin.
7. [Platform readiness 2026-08-21](reviews/platform-readiness-2026-08-21.md):
   phase gate hiện tại và các bằng chứng còn thiếu.
8. [Vận hành worker](operations/worker-observability.md): dashboard, heartbeat,
   retry/dead-letter history và khóa chống chạy trùng.
9. [Checklist triển khai](operations/deployment-checklist.md): cấu hình
   production, backup, migration và release gate trước khi mở người dùng.

## Cấu trúc

```text
docs/
├── architecture/       # Kiến trúc runtime và luồng hệ thống
├── design-system/      # Quy tắc UI, token và component Flutter
├── quality/            # Benchmark, coverage và bằng chứng chất lượng
├── references/         # Tài liệu nguồn được giữ để đối chiếu
├── operations/         # Hướng dẫn CI/CD và vận hành
└── reviews/            # Biên bản đánh giá theo phase/release
```

Tài liệu quality hiện có:

- [Độ phủ tri thức cây trồng](quality/crop-knowledge-coverage.md)
- [Vision benchmark](quality/vision-benchmark.md)
