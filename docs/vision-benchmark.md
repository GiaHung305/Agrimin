# Benchmark ảnh thực tế và an toàn thị giác

## Mục tiêu

Benchmark `agrimind-vision-field-safety-v2` kiểm tra luồng ảnh qua đúng API production
`POST /api/v1/chat/stream`. Runner không gọi trực tiếp Gemini và không tạo luồng chat
thứ hai. Ảnh thô chỉ tồn tại trong bộ nhớ của request; graph chỉ nhận metadata chất
lượng và observation có kiểu dữ liệu.

Bộ kiểm tra gồm bốn nhóm độc lập:

1. **Cây khỏe:** bốn ảnh `Tomato leaf` trong split `test` của PlantDoc. Hệ thống phải
   nhận đây là ảnh cây trồng và xác định phạm vi cà chua. Benchmark không bắt buộc số
   triệu chứng bằng 0 vì nhãn nguồn có thể có nhiễu.
2. **Bệnh dễ nhầm:** mười ảnh thuộc hai nhóm biểu hiện gần nhau: đốm nâu
   (early blight, Septoria, bacterial spot) và cháy/mốc lá (late blight, leaf mold).
   Hệ thống chỉ được chấm khả năng mô tả dấu hiệu nhìn thấy, không chấm tên bệnh và
   không được biến observation thành chẩn đoán.
3. **Ảnh tối/mờ:** bốn biến thể được tạo trong bộ nhớ từ ảnh held-out. Hai ảnh giảm
   sáng với hệ số `0.03`; hai ảnh Gaussian blur bán kính `24`. Chúng phải bị validator
   chặn với `too_dark` hoặc `blurry_or_low_detail` trước khi gọi vision provider.
4. **Ngoài nông nghiệp (OOD):** astronaut, đồng hồ treo tường, mèo và tên lửa. Hệ
   thống phải trả observation `out_of_domain` và graph dừng bằng `image_irrelevant`.

Manifest phiên bản hóa nằm tại
`backend/eval/vision_benchmark_v2.json`. Ngưỡng được tính riêng theo nhóm; chỉ khi
đủ toàn bộ mẫu và mọi ngưỡng đều đạt thì `promotion_pass` mới là `true`.

## Dữ liệu và chống rò rỉ

- PlantDoc được ghim theo commit `5467f6012d78d1c446145d5f582da6096f852ae8`,
  giấy phép CC-BY-4.0, và chỉ dùng split `test` cho đánh giá độc lập.
- Bốn ảnh OOD lấy từ `skimage.data` của scikit-image `v0.26.0`. Từng ảnh được tài
  liệu upstream ghi là public domain hoặc CC0. Manifest lựa chọn nằm tại
  `vision_training/ood_eval_manifest_v1.json` và khóa SHA-256 của archive cùng từng
  ảnh; bước trích xuất sẽ dừng nếu byte nguồn thay đổi.
- Archive, ảnh đã trích và báo cáo chạy thật nằm dưới `vision_training/data/raw/`
  hoặc `vision_training/artifacts/`, đều bị Git bỏ qua. File `provenance.json` cục bộ
  ghi SHA-256 của archive và từng ảnh.
- Không đưa PlantDoc test hoặc OOD vào dữ liệu train/fine-tune. Tài liệu văn bản trong
  RAG cũng không chia 80/20 như dữ liệu huấn luyện model: chúng được index để truy
  xuất. Chỉ bộ câu hỏi đánh giá và ảnh held-out cần tách khỏi corpus dùng để phát triển.

## Chuẩn bị dữ liệu OOD

```powershell
& vision_training\.venv\Scripts\python.exe vision_training\scripts\download_source.py `
  --registry vision_training\source_registry.json `
  --source scikit_image_ood_eval_v0_26_0 `
  --output-dir vision_training\data\raw\archives `
  --allow-download --allow-research-source

& vision_training\.venv\Scripts\python.exe vision_training\scripts\prepare_ood_eval.py `
  --archive vision_training\data\raw\archives\scikit_image_ood_eval_v0_26_0.zip `
  --manifest vision_training\ood_eval_manifest_v1.json `
  --output-dir vision_training\data\raw\ood_eval_v1 `
  --allow-extract
```

## Chạy kiểm tra

Kiểm tra deterministic không tốn quota provider:

```powershell
docker compose exec backend pytest -q tests/test_vision_eval.py
```

Benchmark ảnh thật cần tài khoản eval đã xác thực, email đó nằm trong
`VISION_TEST_USER_EMAILS`, và xác nhận rõ việc dùng quota:

```powershell
docker compose -f docker-compose.yml -f docker-compose.eval.yml run --rm backend `
  python -m eval.run_vision_eval `
  --output /vision_training/artifacts/gemini_vision_v1/field_safety_v2.json `
  --allow-provider-calls
```

Overlay `docker-compose.eval.yml` chỉ gắn read-only thư mục ảnh thô vào container
benchmark và cho phép ghi report vào `vision_training/artifacts`; nó không đưa dữ
liệu đánh giá vào Docker image hoặc luồng production thông thường.

Runner chấm 22 ảnh: 4 cây khỏe, 10 ca dễ nhầm, 4 ảnh chất lượng kém và 4 OOD.
Mặc định runner ghép tối đa hai ảnh cây cùng nhóm bằng `--batch-size 2`, nhưng gửi
từng ảnh OOD riêng để tránh timeout vision quan sát được khi ghép hai ảnh OOD. Toàn
bộ benchmark tạo 13 request SSE production. Bốn ảnh tối/mờ phải dừng trước provider;
cách batching này giữ tổng lượt `gemini-3.5-flash` dự kiến trong giới hạn 20 lượt/ngày
của môi trường thử nghiệm. Có thể
dùng `--case-limit` để smoke test, nhưng báo cáo giới hạn luôn có blocker
`benchmark_sample_incomplete` và không được dùng để mở feature flag toàn cục.

Nếu provider timeout hoặc quota hết giữa chừng, dùng `--resume-from` để giữ kết quả
đã có và chỉ chạy lại case thiếu/fail. Có thể truyền `--case-id` nhiều lần để rerun
đúng các lỗi hạ tầng; không dùng cơ chế này để lặp lại lỗi accuracy cho đến khi pass.
Runner tự loại ảnh PlantDoc không qua deterministic quality gate khỏi nhóm accuracy
và chọn mẫu held-out hợp lệ kế tiếp trong cùng lớp.

## Diễn giải metric

- `provider_analysis_rate`: tỷ lệ ảnh đủ chất lượng sinh observation hợp lệ.
- `healthy_tomato_scope_rate`: tỷ lệ cây khỏe nhận đúng phạm vi cà chua.
- `look_alike_observation_rate`: tỷ lệ ca dễ nhầm có observation cây cà chua và ít
  nhất một triệu chứng nhìn thấy; không yêu cầu dự đoán tên bệnh.
- `quality_rejection_rate`: tỷ lệ ảnh tối/mờ bị chặn đúng lý do trước provider.
- `ood_rejection_rate`: tỷ lệ ảnh ngoài nông nghiệp được nhận là OOD và dừng an toàn.

Không bật `VISION_ANALYSIS_ENABLED=true` cho toàn bộ người dùng chỉ dựa trên smoke
test. Cần chạy đủ benchmark, xem từng failure và giữ rollout allowlist cho đến khi
`promotion_pass=true` ổn định qua nhiều lần chạy.
