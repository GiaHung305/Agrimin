# System Design — AgriMind Virtual Assistant v1

## Mục tiêu

AgriMind chuyển từ hệ thống hỏi đáp sang trợ lý nông nghiệp cá nhân hóa cho một nông trại mỗi tài khoản. Trợ lý hiểu hội thoại đa lượt, dùng RAG và dự báo thời tiết, đề xuất việc hoặc nhật ký và chỉ ghi dữ liệu sau xác nhận.

## Kiến trúc

Flutter giao tiếp FastAPI qua SSE `POST /api/v1/chat/stream`. FastAPI chạy LangGraph gồm planner, guardrail, multi-query retrieval, phân tích coverage/mâu thuẫn, generation, reflection, memory write, action proposal và memory extraction. PostgreSQL lưu lịch sử, hồ sơ nông trại, task, log, action chờ xác nhận, device token và notification. Redis phục vụ cache; Qdrant phục vụ RAG; worker định kỳ tạo in-app notification và gửi FCM khi có credentials.

Embedding service giữ Hugging Face model cache trong named volume để container
recreate không tải lại model. BGE-M3 dùng GPU; reranker dùng CPU với concurrency
giới hạn. Retrieval retry thích ứng: chat low-risk dừng sau lượt đầu nếu thiếu
bằng chứng, Vision có tối đa một lượt mở rộng, còn high-risk hoặc Deep Research
giữ ngân sách tối đa hai lượt. Mọi lượt retry phải dùng query mở rộng mới.

## Luồng chính

1. API xác thực Supabase JWT, lưu message người dùng và nạp tám lượt gần nhất.
2. LangGraph tư vấn bằng hồ sơ nông trại, history, RAG và thời tiết. Draft token
   được giữ trong server đến khi post-guardrail hoàn tất, sau đó câu trả lời đã
   duyệt mới được phát thành các event SSE.
3. Yêu cầu “nhắc tôi” hoặc “ghi nhật ký” tạo `PendingAction` hết hạn sau 15 phút, trả về metadata SSE.
4. Flutter hiển thị thẻ xác nhận. `POST /assistant/actions/{id}/confirm` kiểm tra ownership và chỉ sau đó tạo task/log; cancel chỉ đổi trạng thái action.
5. Worker quét task đến hạn và mưa xác suất từ 70%, ghi notification theo dedupe key; FCM là lớp gửi thêm, không ảnh hưởng notification trong app.

## Internal Research Agent

Planner trả về tối đa bốn `research_questions` trong cùng structured-output call
đang có; hệ thống không gọi thêm model để phân rã câu hỏi. Retriever chạy các
câu hỏi con song song, gắn từng evidence với nhu cầu nghiên cứu đã dẫn tới nó và
tích lũy chunk qua các vòng thay vì ghi đè kết quả trước. Top-k tăng có giới hạn
ở vòng retry.

Node `research_analysis` đánh giá coverage bằng traceability, relevance và source
authority; câu hỏi high-risk chỉ được coi là covered khi có nguồn đủ thẩm quyền.
Coverage chấp nhận reranker đã vượt ngưỡng tin cậy hoặc sự đồng thuận giữa dense
và BM25 khi cross-encoder trả xác suất thấp đồng loạt. Quy tắc này chỉ điều khiển
vòng nghiên cứu; post-guardrail high-risk vẫn dùng ngưỡng nghiêm ngặt hơn.
Node này cũng phát hiện giá trị số cùng đơn vị khác nhau giữa các tài liệu độc
lập và chuyển chúng thành contradiction có thể audit. Thiếu evidence hoặc mâu
thuẫn chỉ được phép tạo tối đa hai retrieval retry; sau đó graph dừng với stop
reason rõ ràng và generation phải nêu phần chưa chắc chắn.

Mọi retrieval retry diễn ra trước generation. Reflection sau generation chỉ chấm
độ bám nguồn và confidence, không được sinh lại câu trả lời. Custom token từ
LangGraph là draft chưa duyệt nên API buffer chúng đến khi post-guardrail hoàn
tất. Nếu guardrail thay draft bằng fallback, chỉ fallback được phát; nếu draft
được duyệt, các chunk cùng phần disclaimer bổ sung được phát theo đúng thứ tự.
Cách này bảo đảm client không nhận nội dung bị guardrail loại và final answer
không diverge khỏi nội dung SSE. Evidence trong prompt được gắn `E1`, `E2`, ...;
citation trả về API mang cùng `citation_id` để truy ngược claim về chunk.

## Multimodal foundation

Flutter cho phép chọn tối đa hai ảnh JPEG, PNG hoặc WebP, preview và xóa ảnh
trước khi gửi. Ảnh đi cùng JSON request trong chính `POST /api/v1/chat/stream`;
không có endpoint chat hay workflow thứ hai. Mỗi ảnh tối đa 4 MB và tổng số
pixel tối đa 16 triệu.

Backend giải mã ảnh trên worker thread, đối chiếu MIME khai báo với magic format,
chặn ảnh nhiều frame/pixel bomb và đo độ phân giải, độ sáng cùng edge variance.
Raw bytes chỉ tồn tại trong request validation và không được đưa vào LangGraph
state, Postgres checkpoint, semantic cache, log hoặc trace. State chỉ giữ hash
rút gọn, kích thước và quality flags; mọi request có ảnh đều bypass semantic
cache.

Luồng hỗ trợ `visual-observation-v1`: output analyzer phải là schema typed gồm
relevance, crop candidate, bộ phận cây, triệu chứng nhìn thấy, giới hạn ảnh và
confidence. Schema cấm field chẩn đoán và cấm mô tả triệu chứng dùng ngôn ngữ
chẩn đoán. Output còn phải khớp chính xác image ID đã xác thực và qua kiểm tra
prompt injection trước khi được đưa vào LangGraph.

Ảnh tối, cháy sáng, quá nhỏ hoặc thiếu chi tiết bị chặn trước planner/model. Ảnh
ngoài miền hoặc quan sát confidence thấp cũng dừng an toàn và yêu cầu dữ liệu bổ
sung. Quan sát đủ tin cậy được dùng để mở rộng truy vấn RAG; generation chỉ được
đưa ra giả thuyết có xếp hạng khi bằng chứng hỗ trợ và phải nêu giới hạn ảnh.
Mô tả trực tiếp đặc điểm nhìn thấy không gắn nguồn giả tạo. Khi người dùng yêu cầu
diễn giải, giả thuyết hoặc xử lý, claim chuyên môn bắt buộc citation truy vết;
dosage vẫn chỉ được phép khi chunk nguồn chính thức hỗ trợ đúng giá trị.

`VISION_ANALYSIS_ENABLED=false` vẫn là mặc định free-tier. Adapter Google Gemini
Flash đã được nối qua `MODEL_VISION`, ép trả `visual-observation-v1` và fail-closed
khi thiếu API key, timeout, hết quota hoặc output sai schema. Global rollout vẫn
default-off nên cấu hình mặc định không phát sinh model call hay chi phí. Email
allowlist có thể chạy typed observation qua đúng production SSE. Challenger
`gemini-3.1-flash-lite` đã vượt benchmark ảnh thật v3 ngày 2026-08-12; model khác
phải có report riêng trước khi promotion.
`VISION_TEST_USER_EMAILS` chỉ cho phép các email được liệt kê chạy analyzer khi
manual QA mà không bật global flag cho người dùng khác. Contract eval
`multimodal-contract-v1` kiểm tra healthy metadata, triệu chứng nhìn thấy, ảnh
thiếu sáng, ảnh ngoài miền và output chẩn đoán không hợp lệ. Benchmark ảnh thật v3
bổ sung PlantDoc held-out, OOD, timeout, nhận nhầm cây, citation claim-level,
uncertainty và cấm liều lượng suy ra từ ảnh; report phải `promotion_pass=true`.

## Deep Research

Deep Research remains on the canonical `POST /api/v1/chat/stream` flow, but its
Google Search Grounding implementation is disabled by default
(`DEEP_RESEARCH_ENABLED=false`) so the free-tier deployment cannot trigger
provider search charges. The Flutter control is hidden unless the app is built
with `--dart-define=ENABLE_DEEP_RESEARCH=true`. When explicitly enabled by an
operator, the response is not semantic-cached and high-risk output remains
buffered until the existing guardrail has validated its evidence.

Internal evidence uses one traceable record from retrieval through the API:
`document_id`, `chunk_id`, `chunk_index`, source/locator, version, active state,
fusion score, and rerank score. High-risk numeric dosage is released only when
the same quantity appears in an active, traceable chunk above the relevance
threshold.

## Evaluation baseline

The evaluator calls the production SSE route and parses complete SSE events,
instead of using a parallel JSON chat endpoint. Golden rows and evaluation runs
are selected by `EVAL_DATASET_VERSION`. Authentication values come only from
`EVAL_USER_EMAIL` and `EVAL_USER_PASSWORD`; no evaluation credential belongs in
source control.

## Model lifecycle

Workflow nodes resolve models by capability role (`planner`, `reflection`,
`generation`, `memory`, `research`, `judge`) through a local model registry.
The current free-tier-compatible champions remain unchanged; changing a model
name is a configuration operation that must pass the versioned evaluation gate
before rollout. Model calls share one asynchronous gateway with bounded retry,
jittered backoff, per-request/read timeout, and a stable SSE fallback.

Semantic-cache namespaces include the model bundle, safety policy, prompt,
evidence schema, knowledge-base version, and an hourly time window. Realtime
weather questions bypass semantic cache entirely.

## Retrieval promotion gate

Retrieval evaluation is independent from answer generation and therefore does
not consume Gemini quota. Dataset `retrieval-v2` measures Recall@K, MRR, nDCG,
and observed latency against the active local knowledge base. The current
pipeline uses Vietnamese accent normalization, BM25Plus, configurable weighted
RRF, placeholder-source exclusion, and a low-confidence reranker fallback that
cannot manufacture a high guardrail score. Any future sparse-vector, ColBERT,
or embedding change must pass `retrieval_baseline_v2.json` before promotion.

Documents also carry a controlled `source_type` from PostgreSQL through Qdrant
and citations. The admin UI can classify new and existing documents as
government, extension, international organization, manufacturer label,
research, user upload, or unknown. Unknown/user-upload evidence cannot satisfy
a high-risk citation requirement. Numeric dosage additionally requires a
government, extension, international, or official manufacturer-label source.

## API

- `GET|PUT /api/v1/assistant/farm-profile`
- `GET /api/v1/assistant/tasks`, `GET /api/v1/assistant/notifications`
- `POST|DELETE /api/v1/assistant/device-tokens`
- `POST /api/v1/assistant/actions/{id}/confirm|cancel`

## Bảo mật và vận hành

Tất cả dữ liệu assistant gắn `user_id`; action ID được kiểm tra ownership, pending status và thời hạn. Prompt injection bị chặn trước DB/model. Firebase credentials chỉ đọc từ biến môi trường/volume, không commit. Backend và worker gọi MCP thời tiết qua `mcp-weather-server:8002`, có timeout và adapter tương thích cả `structuredContent` lẫn SDK cũ. Weather là nguồn phụ: lỗi của một lần tra cứu không làm hỏng chat hoặc rollback toàn bộ chu kỳ reminder. Worker chạy tách backend qua Docker Compose và retry ở chu kỳ sau khi external weather/FCM lỗi.

## Rollout và kiểm thử

Chạy migration Alembic trước deploy, cấu hình Firebase nếu cần push, rồi triển khai backend và worker. Theo dõi cache hit, action confirmation rate, notification delivery và tỷ lệ cảnh báo trùng. Kiểm thử history đa lượt, ownership, action hết hạn, task due, weather dedupe và UI confirm/cancel.
