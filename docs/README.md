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

## Cấu trúc

```text
docs/
├── architecture/       # Kiến trúc runtime và luồng hệ thống
├── design-system/      # Quy tắc UI, token và component Flutter
├── quality/            # Benchmark, coverage và bằng chứng chất lượng
├── references/         # Tài liệu nguồn được giữ để đối chiếu
└── reviews/            # Biên bản đánh giá theo phase/release
```

Tài liệu quality hiện có:

- [Độ phủ tri thức cây trồng](quality/crop-knowledge-coverage.md)
- [Vision benchmark](quality/vision-benchmark.md)
