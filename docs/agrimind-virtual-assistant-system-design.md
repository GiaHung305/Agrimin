# System Design — AgriMind Virtual Assistant v1

## Mục tiêu

AgriMind chuyển từ hệ thống hỏi đáp sang trợ lý nông nghiệp cá nhân hóa cho một nông trại mỗi tài khoản. Trợ lý hiểu hội thoại đa lượt, dùng RAG và dự báo thời tiết, đề xuất việc hoặc nhật ký và chỉ ghi dữ liệu sau xác nhận.

## Kiến trúc

Flutter giao tiếp FastAPI qua SSE `POST /api/v1/chat/stream`. FastAPI chạy LangGraph gồm planner, guardrail, multi-query retrieval, phân tích coverage/mâu thuẫn, generation, reflection, memory write, action proposal và memory extraction. PostgreSQL lưu lịch sử, hồ sơ nông trại, task, log, action chờ xác nhận, lịch theo dõi, observation, prediction, recommendation, device token và notification. Redis phục vụ cache; Qdrant phục vụ RAG; worker định kỳ tạo in-app notification và gửi FCM khi có credentials.

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
5. Worker quét task đến hạn và lịch theo dõi đã được người dùng đồng ý. Mỗi lần chạy lưu observation thời tiết, prediction theo policy có phiên bản và recommendation trước khi ghi notification theo dedupe key; FCM chỉ chạy nếu người dùng chọn kênh push.

## Farm monitoring Phase 4

Phạm vi theo dõi phủ mọi tỉnh Việt Nam và mọi cây trồng có tên trong mùa vụ. Các
cây phổ biến (cà chua, lúa, cà phê, hồ tiêu, sầu riêng, ớt, ngô, sắn, chuối,
xoài, thanh long và cây có múi) có policy riêng theo nhóm rủi ro mưa/ẩm/nóng;
cây chưa có policy riêng dùng `generic-weather-watch-v1`. Policy dự phòng chỉ
cảnh báo điều kiện thời tiết và yêu cầu kiểm tra ruộng, không suy diễn bệnh hoặc
đề xuất hóa chất. Trạng thái canh tác được tách thành farm profile, nhiều thửa
đất và lịch sử mùa vụ; mỗi thửa chỉ có tối đa một mùa vụ active. Lịch theo dõi
bắt buộc trỏ đến một mùa active thuộc đúng user và farm. Kết thúc hoặc đổi cây
trong mùa tự pause lịch để người dùng xác nhận lại policy trước khi tiếp tục.
Registry vùng dùng 34 đơn vị cấp tỉnh theo Quyết định 19/2025/QĐ-TTg và vẫn ánh
xạ tên tỉnh cũ trước sáp nhập để hồ sơ hiện có không mất khả năng theo dõi.

Mỗi thửa có thể lưu cặp tọa độ GPS tùy chọn cùng độ chính xác, cao độ, nguồn
`device|manual` và thời điểm cập nhật. Flutter chỉ xin quyền vị trí khi người dùng
chủ động bấm lấy GPS; hệ thống không theo dõi vị trí nền. Worker ưu tiên tọa độ
của đúng thửa và đúng `user_id`; thửa cũ chưa có GPS tiếp tục dùng tọa độ đại
diện của tỉnh. Observation ghi rõ `plot_gps|province_geocode` để việc đánh giá và
truy vết nguồn tọa độ không bị nhập nhằng.

Registry rau có 80 policy được nhận diện riêng bằng alias tiếng Việt không dấu,
có dấu và tiếng Anh. Phạm vi gồm rau ăn lá (các loại cải, xà lách, rau muống,
mồng tơi, rau dền, rau ngót...), họ cải, rau ăn thân/hoa, cà–ớt, dưa–bí, rau họ
đậu, rau củ, củ lấy tinh bột, hành–tỏi, rau gia vị và thân rễ. Mỗi loại có
`policy_key`, version, nhãn hiển thị và nhóm riêng; các loại cùng nhóm chia sẻ
ranh giới weather-watch bảo thủ. Nguồn nền về nhu cầu nước/nhóm cây lấy từ bảng
crop factor của FAO; hành–tỏi có thêm nguồn FAO riêng về quan hệ nước của hành.
Không có policy nào tự suy ra bệnh, kê thuốc hoặc tự tạo công việc.

Người dùng phải chủ động bật lịch, chọn chu kỳ 6, 12 hoặc 24 giờ và phạm vi thông
báo trong app hoặc kèm push. API cho phép xem, tạm dừng, tiếp tục và soft-delete
lịch; audit cũ không bị xóa theo lịch. Thửa có mùa active hoặc schedule chưa xóa
không thể archive, và mùa có schedule chưa xóa không thể bị xóa để tránh orphan.

Registry policy là deterministic và có version. Ngưỡng vận hành chung tạo cảnh
báo cao khi tổng mưa ngày từ 50 mm hoặc xác suất mưa cực đại từ 85%; nhóm cây
nhạy ẩm còn cảnh báo cao khi xác suất mưa từ 50% đồng thời độ ẩm cực đại từ 85%,
nhóm nóng/thời tiết cảnh báo cao từ 38°C. Đây là ranh giới vận hành bảo thủ để
ưu tiên kiểm tra thực địa, không phải ngưỡng chẩn đoán sinh học. OpenWeather 5
day/3 hour được tổng hợp từ mọi mốc trong ngày thành nhiệt độ min/max, độ ẩm max,
xác suất mưa max và tổng `rain.3h`, thay vì chỉ lấy mốc đầu tiên.

Confidence được tính động từ độ đầy đủ của bốn chỉ dấu và khoảng cách tới ngưỡng;
đây là độ tin cậy của phép đánh giá policy, không phải xác suất cây đã mắc bệnh.
Prediction lưu `policy_key`, crop, province, reasons và URL nguồn để truy vết.
Nguồn nền gồm tài liệu OpenWeather về forecast 3 giờ, FAO về úng/thoát nước và
nắng nóng, cùng IRRI về quản lý nước lúa. Notification luôn yêu cầu kiểm tra tại
ruộng và nêu rõ không phải chẩn đoán hoặc chỉ định hóa chất. `run_key` của
observation và dedupe key theo schedule/ngày/policy ngăn retry tạo bản ghi trùng.

Push delivery dùng transactional outbox `notification_deliveries`. Worker ghi
notification và từng delivery theo device vào PostgreSQL trong cùng transaction;
không gọi FCM trước commit. Chu kỳ delivery riêng khóa row với `SKIP LOCKED`, chỉ
gửi cho token active thuộc cùng user, retry exponential tối đa năm lần và lưu
attempt count, lỗi cuối cùng cùng thời điểm delivered. In-app notification không
phụ thuộc FCM và vẫn tồn tại nếu push thất bại.

Recommendation nguy cơ tạo một `PendingAction` có cùng thời hạn. Người dùng có
thể chọn Tạo việc hoặc Bỏ qua trong màn Thông báo; `FarmTask` chỉ được ghi sau
xác nhận đúng owner. Worker tự chuyển recommendation và pending action quá hạn
sang `expired`, kể cả khi người dùng không mở ứng dụng.

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
- `GET|POST /api/v1/assistant/plots`, `PATCH|DELETE /api/v1/assistant/plots/{id}`
- `POST /api/v1/assistant/plots/{id}/seasons`, `PATCH|DELETE /api/v1/assistant/seasons/{id}`
- `GET /api/v1/assistant/tasks`, `GET /api/v1/assistant/notifications`
- `GET|POST /api/v1/assistant/monitoring-schedules`
- `PATCH|DELETE /api/v1/assistant/monitoring-schedules/{id}`
- `POST|DELETE /api/v1/assistant/device-tokens`
- `POST /api/v1/assistant/actions/{id}/confirm|cancel`

## Bảo mật và vận hành

Tất cả dữ liệu assistant gắn `user_id`; action, plot, season, monitoring schedule và push delivery đều kiểm tra ownership. Action còn phải đúng pending status và thời hạn. Prompt injection bị chặn trước DB/model. Firebase credentials chỉ đọc từ biến môi trường/volume, không commit. Backend và worker gọi MCP thời tiết qua `mcp-weather-server:8002`, có timeout và adapter tương thích cả `structuredContent` lẫn SDK cũ. Logger `httpx` của weather/geocoding bị giới hạn ở WARNING để query string chứa `appid` không vào log. Weather là nguồn phụ: lỗi của một lần tra cứu không làm hỏng chat hoặc rollback toàn bộ chu kỳ reminder. Worker chạy tách backend qua Docker Compose và retry lịch lỗi sau 15 phút.

## Rollout và kiểm thử

Chạy migration Alembic trước deploy, cấu hình Firebase nếu cần push, rồi triển khai backend, MCP weather và worker. Theo dõi cache hit, action confirmation rate, monitoring failure, notification delivery và tỷ lệ cảnh báo trùng. Kiểm thử history đa lượt, ownership, action hết hạn, task due, schedule consent/pause/delete, worker idempotency, prediction expiry và UI confirm/cancel.
