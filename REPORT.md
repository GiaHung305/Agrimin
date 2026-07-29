# Báo cáo dự án AgriMind

## 1. Tổng quan

AgriMind là một hệ thống AI hỏi đáp chuyên biệt cho lĩnh vực nông nghiệp. Dự án nhằm kết hợp các công nghệ hiện đại như RAG, LangGraph, vector search và tool calling để cung cấp câu trả lời có căn cứ, có chú thích nguồn và có kiểm soát an toàn.

## 2. Mục tiêu hệ thống

- trả lời câu hỏi liên quan đến nông nghiệp một cách hữu ích;
- sử dụng tài liệu chuyên môn đã được ingest thay vì phụ thuộc hoàn toàn vào trí nhớ model;
- giảm hallucination bằng guardrail và reflection;
- tối ưu trải nghiệm bằng caching và memory.

## 3. Kiến trúc hệ thống

### 3.1 Frontend
Frontend được xây dựng bằng Flutter, đảm nhiệm giao diện người dùng và gọi API backend.

### 3.2 Backend
Backend dùng FastAPI làm entry point. Nó chịu trách nhiệm:
- xác thực người dùng;
- quản lý hội thoại;
- khởi tạo workflow agent;
- gọi retrieval và generation;
- trả về kết quả có trace và metadata.

### 3.3 Workflow agent
Workflow được triển khai bằng LangGraph với các node chính:
- Planner: phân loại câu hỏi và xác định cần công cụ nào
- Pre-guardrail: đặt các điều kiện kiểm soát trước
- Retrieve: tìm tài liệu liên quan
- Generate: tạo câu trả lời
- Reflection: tự kiểm tra câu trả lời
- Post-guardrail: chặn hoặc cho phép trả lời
- Fallback: phản hồi an toàn khi không đủ dữ liệu
- Memory write/extract: lưu ngữ cảnh người dùng

### 3.4 Retrieval và RAG
Hệ thống dùng hybrid retrieval gồm:
- dense search trên Qdrant;
- BM25 keyword search;
- reranking để sắp xếp lại kết quả;
- semantic cache bằng Redis để tăng tốc.

### 3.5 Data layer
- PostgreSQL: lưu thông tin người dùng, hội thoại, tài liệu, memory, eval
- Redis: cache câu trả lời và ngữ cảnh
- Qdrant: lưu vector embedding của chunk tài liệu

### 3.6 External services
- Embedding service riêng: chạy model embedding và reranker
- MCP weather server: cung cấp dữ liệu thời tiết cho câu hỏi liên quan đến thời tiết
- Supabase Auth: xác thực người dùng qua JWT
- Langfuse: theo dõi trace và giám sát hoạt động

## 4. Luồng hoạt động

1. Người dùng nhập câu hỏi từ frontend.
2. Backend xác thực người dùng và tạo hoặc lấy conversation.
3. Planner xác định mức độ rủi ro và có cần dùng RAG/ thời tiết hay không.
4. Retriever tìm tài liệu liên quan.
5. Generator tạo câu trả lời dựa trên tài liệu và ngữ cảnh.
6. Reflection kiểm tra câu trả lời có đủ bám sát tài liệu không.
7. Guardrail quyết định cho phép trả lời hay dùng fallback.
8. Hệ thống lưu memory và cache nếu phù hợp.

## 5. Cấu trúc thư mục

```text
backend/
  app/
    api/           # endpoint FastAPI
    core/          # config, auth, db, redis, qdrant
    repository/    # ORM models
    retrieval/     # search và chunking
    services/      # ingest, embedding, storage, cache
    tools/         # integration với external tools
    workflow/      # LangGraph và các node
  tests/          # unit tests

embedding-service/
frontend_flutter/

docker-compose.yml
```

## 6. Những gì đã hoàn thành

Dự án hiện đã có nền tảng MVP khá đầy đủ:
- kiến trúc backend rõ ràng và module hóa;
- API chat và document ingestion;
- workflow agent với planning, retrieval, generation, reflection và guardrail;
- retrieval đa tầng bằng vector search và rerank;
- tích hợp Qdrant, Redis, PostgreSQL;
- memory và cache cho trải nghiệm tốt hơn;
- frontend cơ bản;
- test và eval pipeline.

## 7. Điểm mạnh

- kết hợp nhiều công nghệ hiện đại phù hợp cho AI application;
- có khả năng mở rộng thêm tool mới như weather, advisory, disease diagnosis;
- có guardrail giúp giảm lỗi và tăng độ tin cậy;
- tách biệt rõ service embedding và backend để dễ triển khai.

## 8. Hạn chế và hướng phát triển

- cần bổ sung UI đầy đủ hơn cho trải nghiệm người dùng;
- cần thu thập dữ liệu thực tế và đánh giá chất lượng hơn bằng golden dataset;
- cần bổ sung thêm tool chuyên sâu cho nông nghiệp;
- cần tối ưu hiệu suất và triển khai production-ready cấu hình.

## 9. Kết luận

AgriMind đã bước từ ý tưởng thành một hệ thống MVP hoàn chỉnh về mặt kiến trúc và chức năng cốt lõi. Đây là một nền tảng tốt để phát triển thành sản phẩm AI dành cho người dùng nông nghiệp thực tế.
