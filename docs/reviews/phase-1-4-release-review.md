# Review phát hành Phase 1–4

Cập nhật: 2026-08-20. Tài liệu này phân biệt phần đã được chứng minh bằng code/test
với benchmark cần quota provider. Không dùng smoke test giới hạn mẫu để tuyên bố
promotion.

## Kết luận hiện tại

AgriMind đang ở cuối Phase 4, trạng thái release candidate. Chức năng và cổng
promotion tự động của cả bốn phase đã hoàn tất trên challenger fingerprint
`cb3562e84674bbe8` (`safety-v7/prompts-v7/kb-v3`, text role
`gemini-3.5-flash-lite`). Backend champion `412d147e35598d2c` dùng model khác và
không kế thừa report này. Phần còn lại là chọn/promote cấu hình model, rollout
theo đợt, quan sát vận hành và soak worker; challenger không còn blocker quota.

## Ma trận bằng chứng

| Phase | Phạm vi đã có | Bằng chứng hiện tại | Cổng còn mở |
| --- | --- | --- | --- |
| 1 — RAG và an toàn | Typed workflow, citation theo evidence, provider fallback/circuit breaker theo role, early guardrail trước planner, guardrail trước/sau generation, parser liều/rate/tỷ lệ tập trung, memory/checkpoint, atomic replacement và purge hai giai đoạn có tombstone retry, golden eval v2 với judge >=0,70 | Full backend 363/363; golden v2 10/10, accuracy/citation/guardrail 100%; migration ở `head`, Alembic sạch | Không còn blocker chức năng; theo dõi production |
| 2 — Internal Research | Phân rã tối đa 4 câu hỏi, coverage/authority/freshness/contradiction, tối đa 2 retry, citation truy vết và theo claim, promotion gate latency | Benchmark production đủ 20 ca đạt promotion ở 95%; citation match/traceable/research/safety 100%, p95 21,41 giây | Residual P1: câu sầu riêng đôi khi đi quá sâu sang xử lý và bỏ nhánh héo ngọn |
| 3 — Vision | Validation ảnh, typed observation, OOD/ảnh tối-mờ/look-alike, crop ambiguity guard, dosage fail-closed, model/fingerprint lifecycle | Fingerprint hiện tại đạt đủ 24/24: grounded/citation/guardrail/safe answer 100%, quality/OOD 100%, timeout 0%, p95 42,968 giây | Global flag vẫn tắt để rollout theo đợt, không phải blocker benchmark |
| 4 — Farm Agent | Farm/plot/season/consent, scheduler, weather observation, prediction version/confidence/expiry, pending action, dedupe, outbox, pause/delete/audit | Bộ schema/ownership/Farm Agent `53 passed`; worker dùng savepoint theo schedule; confirm/cancel/expiry khóa row cùng thứ tự; ORM và PostgreSQL không còn schema drift | Theo dõi worker soak dài hơn trong môi trường triển khai |

## Cổng phát hành không tốn quota đã đạt

- `docker compose exec -T backend pytest -q`: 363/363 test đạt.
- Migration `i9e53a1f86b4` thêm index ownership/due-work; cả `downgrade`
  về `h8d42f0e75a3` và `upgrade head` đều đạt.
- `docker compose exec -T backend alembic check`: `No new upgrade operations
  detected`; bốn bảng checkpoint do LangGraph quản lý được loại đúng khỏi
  Alembic autogenerate.
- Retrieval production-source gate: Recall@1/K, MRR và nDCG đều 1,0; mean
  latency 4.715,90 ms; mọi check đạt.
- `flutter analyze --no-pub lib`: không có issue.
- `flutter build apk --debug`: tạo được `app-debug.apk`.
- Bốn ca guardrail gọi đúng `POST /api/v1/chat/stream` với fingerprint
  `ede60fac222b6dfc`: 4/4 đạt, confidence 0, p50 0,49 giây, p95/max 0,51
  giây. Ba ca liều thiếu ngữ cảnh có `planner.need_rag=null`, chứng minh early
  guardrail đã dừng trước planner/provider; ca prompt injection dừng ngay tại API.
- Backend, worker, embedding, weather, PostgreSQL, Redis và Qdrant đang chạy;
  worker không có lỗi startup sau khi nạp code mới.
- Runtime đã nạp eval `v2`, Vision `gemini-3.1-flash-lite`, text challenger
  `gemini-3.5-flash-lite`, policy `safety-v7`, prompts `prompts-v7`, KB `kb-v3`;
  Vision global vẫn tắt.
- `git diff --check` sạch và không có pattern secret mạnh trong tracked diff.

## Cổng dùng quota đã đạt

Các report dưới đây gọi đúng workflow production trên service challenger tách
biệt, không phải luồng chat sản phẩm thứ hai, và cùng fingerprint
`cb3562e84674bbe8`:

- Agriculture 20 ca: `promotion_pass=true`, 19/20 ca đạt; pass rate 95%, citation
  match/traceable/research/safety 100%, p95 21,41 giây.
- Golden v2: 10/10, accuracy/citation/guardrail 100%, gate đạt.
- Vision v3: đủ 24 ảnh, `promotion_pass=true`; grounded/citation/guardrail/safe
  answer 100%, timeout 0%, p95 42,968 giây.

Runner checkpoint nguyên tử và chỉ resume report có cùng dataset, model và runtime
fingerprint. Không ghép kết quả champion/challenger hoặc fingerprint khác.

Tên report runtime cuối:

- `agriculture_benchmark_challenger_safety_v7_prompts_v7_kbv3_2026-08-20.json`;
- `golden_eval_challenger_safety_v7_prompts_v7_kbv3_2026-08-20.json`;
- `phase3-production-safety-v7-prompts-v7-kbv3_2026-08-20.json`.

Các file report bị Git ignore. Khi model, policy, prompt, evidence schema hoặc KB
đổi phiên bản, phải tạo report mới; report cũ chỉ là bằng chứng lịch sử.

## Quyết định rollout

- Có thể cho test user tiếp tục dùng với Vision allowlist.
- Điều kiện benchmark để bật Vision theo đợt đã đạt; `VISION_ANALYSIS_ENABLED`
  vẫn default-off cho đến khi người vận hành chủ động rollout và bật monitoring.
- Trước rollout rộng phải hoặc promote đúng cấu hình challenger đã đánh giá, hoặc
  chạy lại toàn bộ gate cho champion `412d147e35598d2c`; không trộn fingerprint.
- Phase 1–4 hoàn tất ở mức release candidate. Production GA còn phụ thuộc chọn
  model, soak worker, quan sát lỗi/chi phí và rollout tăng dần.
