# Ma trận độ phủ kiến thức cây trồng

AgriMind quản lý độ phủ dữ liệu theo bốn chiều: **cây trồng × chủ đề × giai
đoạn × vùng sinh thái**. Cách này tách rõ việc hệ thống “biết tên nhiều cây” với
việc có đủ bằng chứng chuyên biệt để tư vấn từng cây.

## Ảnh chụp hiện tại

- 91 cây có chính sách theo dõi, gồm cây trồng chính và danh mục rau mở rộng.
- 130/130 nguồn đang hoạt động đã được phân loại; không có nguồn chưa kiểm duyệt,
  thiếu trong kho hoặc sai `source_type`.
- 17.836 ô cần phủ: 859 ô có nguồn đúng cả giai đoạn và vùng, 13.371 ô chỉ có
  tài liệu nền toàn quốc/toàn vụ, và 3.606 ô chưa có bằng chứng phù hợp.
- Backlog hiện không còn P0 hoặc P1; 91/91 cây ở P2 theo công thức kiểm toán hiện
  tại. P2 nghĩa là cây đã có ít nhất hai nguồn chuyên biệt và không còn từ ba
  chủ đề trở lên hoàn toàn trống; không có nghĩa là đã hoàn chỉnh mọi vùng/vụ.
- Không còn cây nào có `topic_gaps`; backlog còn lại là chiều sâu theo giai đoạn
  và vùng sinh thái.

## Lô mở rộng rau số 1

Lô `crop-data-expansion-batch-1-v1` bổ sung 10 tài liệu đã tách theo cây từ ba
nguồn chính thức của Khuyến nông TP.HCM và Khuyến nông Đà Nẵng. Lô này tạo bằng
chứng chuyên biệt cho khổ qua, dưa leo, bí đao, bí đỏ, bầu, ớt, cà tím, đậu cô
ve, đậu đũa, rau muống, cải xanh và xà lách; đồng thời bổ sung nguồn thứ hai cho
cải ngọt.

Các phần trong cẩm nang rau ăn quả được cắt bằng marker tiêu đề, vì nhiều cây
bắt đầu ở giữa trang PDF. Bản tách đầu tiên thiếu tiêu đề cà tím đã được thay
thế bằng phiên bản `crop-fruit-manual-split-v2`; bản cũ chỉ bị vô hiệu hóa mềm.
Benchmark 12 truy vấn đạt recall@1 = 100%, recall@3 = 100%, MRR = 100% và
nDCG@3 = 99,33%, với độ trễ trung bình khoảng 4,05 giây.

Các artefact kiểm toán gồm:

- `backend/eval/crop_data_expansion_batch_1_v1.json`
- `backend/eval/crop_data_expansion_batch_1_report.json`
- `backend/eval/retrieval_dataset_crop_expansion_batch_1_v1.json`
- `backend/eval/retrieval_report_crop_expansion_batch_1_v1.json`

Nguồn nhãn được lưu tại
`backend/eval/crop_knowledge_source_tags_v1.json`; báo cáo và backlog sinh ra ở
`backend/eval/crop_knowledge_coverage_report_v1.json`.

## Lô mở rộng cây trồng số 2

Lô `crop-data-expansion-batch-2-v1` bổ sung 6 tài liệu kỹ thuật chính thức của
Trung tâm Khuyến nông Quốc gia cho ngô, khoai tây, ớt chuông/ớt ngọt, mồng tơi
và nhóm rau họ cải. Nguồn nhóm rau họ cải bổ sung bằng chứng phòng trừ sâu tơ
cho súp lơ xanh, súp lơ trắng, su hào, bắp cải, cải ngọt và cải xanh. Tài liệu
ngô gồm cả quy trình canh tác và IPM sâu keo mùa thu.

Đối soát sau ingest ghi nhận 6/6 tài liệu active, 24 chunk trong PostgreSQL và
24 point tương ứng trong Qdrant. Một phiên bản ớt ngọt cũ được vô hiệu hóa mềm
sau khi bổ sung alias “ớt chuông/bell pepper”; chạy lại manifest cho kết quả
`already_active = 6`, không tạo dữ liệu trùng.

Benchmark 8 truy vấn đạt recall@1 = 87,5%, recall@3 = 100%, MRR = 93,75% và
nDCG@3 = 96,17%. Bốn gate chất lượng đều đạt. Gate hiệu năng chưa đạt: lượt
gần nhất có độ trễ trung bình 12,57 giây so với ngưỡng 10 giây; độ trễ từng câu
dao động 4,32–26,63 giây trong môi trường reranker CPU đang thiếu bộ nhớ. Không
nới ngưỡng để hợp thức hóa kết quả; cần tối ưu hoặc kiểm tra lại trên máy đã
giải phóng RAM.

Các artefact kiểm toán gồm:

- `backend/eval/crop_data_expansion_batch_2_v1.json`
- `backend/eval/crop_data_expansion_batch_2_report.json`
- `backend/eval/retrieval_dataset_crop_expansion_batch_2_v1.json`
- `backend/eval/retrieval_report_crop_expansion_batch_2_v1.json`

## Lô mở rộng rau số 3

Lô `crop-data-expansion-batch-3-v1` bổ sung 17 đoạn tài liệu từ 11 nguồn chính
thức cho 12 cây P0: rau dền, măng tây, su su, rau ngót, củ cải trắng, dưa lưới,
dưa hấu, đậu Hà Lan, đậu bắp, ngô ngọt, hành tây và hành lá. Các tài liệu được
tách theo phần canh tác hoặc thu hoạch để mỗi chunk giữ đúng ngữ cảnh cây và
giai đoạn.

Hai cẩm nang cũ có phần khuyến cáo thuốc không còn phù hợp đã được cắt ở mức
trang/marker trước khi ingest. Corpus lô này không chứa Paraquat, Carbendazin,
Metalaxyl, Cypermethrin, Fipronil, Benlat, Aliette, Vicarben, Confidor, Regent
hoặc GA3. Nguồn su su chỉ giữ triệu chứng, nguyên nhân và biện pháp canh tác;
nguồn hành kết thúc trước danh sách thuốc cũ.

Đối soát sau ingest ghi nhận 17/17 tài liệu active, 36 chunk trong PostgreSQL
và 36 point tương ứng trong Qdrant. Ma trận strict tăng lên 49/49 nguồn được
phân loại; số cây P0 giảm từ 60 xuống 48 và số ô chưa có bằng chứng phù hợp
giảm từ 4.264 xuống 4.016.

Benchmark 18 truy vấn đạt recall@1 = 100%, recall@3 = 100%, MRR = 100% và
nDCG@3 = 100%. Gate độ chính xác đạt toàn bộ. Gate hiệu năng chưa đạt vì độ
trễ trung bình 10,94 giây so với ngưỡng 10 giây; các truy vấn đầu chịu thời
gian nạp reranker CPU, trong khi 11 truy vấn cuối dao động khoảng 4,1–5,1 giây.

Các artefact kiểm toán gồm:

- `backend/eval/crop_data_expansion_batch_3_v1.json`
- `backend/eval/crop_data_expansion_batch_3_report.json`
- `backend/eval/retrieval_dataset_crop_expansion_batch_3_v1.json`
- `backend/eval/retrieval_report_crop_expansion_batch_3_v1.json`

## Lô mở rộng rau gia vị số 4

Lô `crop-data-expansion-batch-4-v1` bổ sung 10 đoạn canh tác chuyên biệt từ
cẩm nang chính thức của Trung tâm Khuyến nông TP.HCM cho diếp cá, húng cây,
húng quế, kinh giới, ngò gai, rau răm, tía tô, thì là, lá lốt và ngò rí. Các
tên đồng nghĩa tiếng Việt/Anh được đặt trong từng đoạn để phân biệt các cây dễ
nhầm như húng cây với húng quế, hoặc ngò gai với ngò rí.

Mỗi đoạn bắt đầu tại tiêu đề riêng của cây và kết thúc trước mục `Phòng trừ sâu
bệnh`. Vì vậy danh sách thuốc BVTV ở từng mục, phần địa chỉ cung cấp giống và
danh bạ điện thoại cuối cẩm nang không đi vào corpus. Quét nội dung sau tách
không phát hiện tên thuốc cũ trong danh sách kiểm soát, email hoặc số điện thoại.

Đối soát sau ingest ghi nhận 10/10 tài liệu active, 10 chunk trong PostgreSQL và
10 point tương ứng trong Qdrant. Chạy lại manifest cho kết quả
`already_active = 10`, không tạo dữ liệu trùng. Ma trận strict tăng lên 50/50
nguồn được phân loại; số cây P0 giảm từ 48 xuống 38, số cây P1 tăng từ 35 lên
45 và số ô có bằng chứng phù hợp tăng từ 722 lên 782.

Benchmark 10 truy vấn đạt recall@1 = 100%, recall@3 = 100%, MRR = 100% và
nDCG@3 = 100%; không có nhầm top-1 giữa các rau gia vị. Gate hiệu năng chưa đạt:
lượt đầu có độ trễ trung bình 17,10 giây và lượt đo lại 19,19 giây, đều cao hơn
ngưỡng 10 giây. Những truy vấn đầu có thể mất 35–44 giây trong khi các truy vấn
cuối thường khoảng 5,5–8,4 giây; kết quả đo lại cho thấy nút thắt reranker CPU
không chỉ là cold-start và cần được tối ưu riêng.

Các artefact kiểm toán gồm:

- `backend/eval/crop_data_expansion_batch_4_v1.json`
- `backend/eval/crop_data_expansion_batch_4_report.json`
- `backend/eval/retrieval_dataset_crop_expansion_batch_4_v1.json`
- `backend/eval/retrieval_report_crop_expansion_batch_4_v1.json`
- `backend/eval/retrieval_report_crop_expansion_batch_4_warm_v1.json`

## Lô mở rộng cây lương thực, củ và gia vị số 5

Lô `crop-data-expansion-batch-5-v1` bổ sung 13 tài liệu đã tách từ 8 nguồn chính
thức cho lạc/đậu phộng, đậu tương/đậu nành, khoai lang, sắn/khoai mì, nghệ,
gừng, rau má và tỏi. Tên tiếng Việt, tên đồng nghĩa phổ biến, tên tiếng Anh và
tên khoa học được thêm vào từng tài liệu để giảm nhầm cây khi truy hồi.

Các PDF lạc và đậu tương chỉ lấy chương canh tác cùng phần thu hoạch, kết thúc
trước chương thuốc BVTV cũ. Nguồn khoai lang bỏ đoạn xử lý đất bằng hóa chất và
đoạn sử dụng ngoài phạm vi cây trồng. Nguồn sắn bỏ các mục thuốc, thuốc cỏ và
thức ăn chăn nuôi. Nguồn nghệ bỏ xử lý hom bằng thuốc nấm và mục phòng trừ sâu
bệnh. Với gừng, lát dữ liệu bắt đầu sau toàn bộ mục xử lý hom có Validacine,
Topsin và Dithane, rồi kết thúc trước mục phòng trừ sâu bệnh. Các nguồn rau má
và tỏi cũng kết thúc trước danh mục thuốc cũ; phần tuyên bố y học và đoạn thu
hoạch quá ngắn của tỏi không được ingest.

Quét trực tiếp 13 nội dung sau khi cắt không phát hiện tên thuốc cũ trong danh
sách kiểm soát, email hoặc số điện thoại. Đối soát sau ingest ghi nhận 13/13 tài
liệu active, 22 chunk trong PostgreSQL và 22 point tương ứng trong Qdrant. Chạy
lại manifest cho kết quả `already_active = 13`, không tạo dữ liệu trùng. Ma
trận strict tăng lên 58/58 nguồn được phân loại; số cây P0 giảm từ 38 xuống 30,
số cây P1 tăng từ 45 lên 53 và số ô có bằng chứng phù hợp tăng từ 782 lên 794.

Benchmark 14 truy vấn đạt recall@1 = 100%, recall@3 = 100%, MRR = 100% và
nDCG@3 = 100%. Độ trễ trung bình là 8,45 giây nên gate hiệu năng 10 giây đạt;
truy vấn đầu tiên vẫn chậm 25,72 giây do tải reranker CPU, vì vậy độ trễ đuôi
vẫn cần được theo dõi ở bước tối ưu tiếp theo.

Các artefact kiểm toán gồm:

- `backend/eval/crop_data_expansion_batch_5_v1.json`
- `backend/eval/crop_data_expansion_batch_5_report.json`
- `backend/eval/retrieval_dataset_crop_expansion_batch_5_v1.json`
- `backend/eval/retrieval_report_crop_expansion_batch_5_v1.json`

## Lô mở rộng cây trồng số 6

Lô `crop-data-expansion-batch-6-v1` bổ sung 10 tài liệu từ 7 nguồn chính
thống cho 7 cây P0: chuối, khoai môn, mướp, atisô, hẹ, cải bó xôi và cần
tây. Các bài HTML được tách theo marker trong phần nội dung hiển thị; mã script,
style và nội dung ngoài lát được kiểm soát không đi vào corpus. Quy trình atisô
dùng phụ lục năm 2024 trên Cơ sở dữ liệu quốc gia về văn bản pháp luật.

Các lát dữ liệu kết thúc trước danh mục thuốc bảo vệ thực vật, tuyên bố y học
hoặc thông tin liên hệ không cần thiết. Quét trực tiếp toàn bộ 10 nội dung sau
khi tách không phát hiện tên hóa chất cũ trong danh sách kiểm soát, email hoặc
số điện thoại. Một nguồn cải thìa trả HTTP 404 và một nguồn cải bắp có chuỗi
chứng thư TLS không hợp lệ đã bị loại, không hạ kiểm tra TLS để cố ingest.

Đối soát sau ingest ghi nhận 10/10 tài liệu active, 19 chunk trong PostgreSQL và
19 point tương ứng trong Qdrant. Chạy lại manifest cho kết quả
`already_active = 10`, không tạo dữ liệu trùng. Ma trận strict tăng lên 65/65
nguồn được phân loại; số cây P0 giảm từ 30 xuống 23, số cây P1 tăng từ 53 lên
60, số ô có bằng chứng phù hợp tăng từ 794 lên 803 và số ô gap giảm từ 3.775
xuống 3.724.

Benchmark 10 truy vấn đạt recall@1 = 100%, recall@3 = 100%, MRR = 100% và
nDCG@3 = 99,20%. Độ trễ trung bình là 8,46 giây nên gate hiệu năng 10 giây đạt.
Truy vấn khởi động đầu tiên vẫn mất 24,34 giây; vì vậy độ trễ đuôi và việc nạp
reranker trên CPU vẫn là rủi ro cần tối ưu, dù không có timeout trong lượt đo.

Các artefact kiểm toán gồm:

- `backend/eval/crop_data_expansion_batch_6_v1.json`
- `backend/eval/crop_data_expansion_batch_6_report.json`
- `backend/eval/retrieval_dataset_crop_expansion_batch_6_v1.json`
- `backend/eval/retrieval_report_crop_expansion_batch_6_v1.json`

## Lô mở rộng rau và cây củ số 7

Lô `crop-data-expansion-batch-7-v1` bổ sung 12 tài liệu được tách từ 7 nguồn
chính thức cho 7 cây P0: rau đay, cải thảo/cải bao, cải cúc/tần ô, củ dền đỏ,
đậu rồng/đậu khế, hành tím và củ đậu/củ sắn nước. Mỗi tài liệu có tên đồng nghĩa
tiếng Việt, tiếng Anh và tên khoa học phù hợp để giảm nhầm cây trong truy hồi.

Nguồn rau đay kết thúc trước bảng phân bón và mục thuốc cũ. Nguồn cải thảo chỉ
giữ quy trình rau an toàn cùng IPM canh tác, thủ công, hàng rào và bẫy
pheromone; danh sách thuốc phía sau bị loại. Nguồn cải cúc được tách lại thành
hai lát để loại cả tên chế phẩm `R6`, thay vì chỉ dựa vào việc không có liều.
Nguồn đậu rồng chỉ giữ sinh trưởng cơ bản và quản lý ốc bằng thu gom/bẫy vật
lý; công thức nước rửa chén và toàn bộ thuốc bị loại. Nguồn củ đậu kết thúc
trước câu khuyến nghị phun thuốc định kỳ. Quét 12 nội dung sau tách không phát
hiện tên hóa chất/chế phẩm trong danh sách kiểm soát, công thức chất tẩy rửa,
email hoặc số điện thoại.

Đối soát sau ingest ghi nhận 12/12 tài liệu active, 13 chunk trong PostgreSQL
và 13 point tương ứng trong Qdrant. Chạy lại manifest cho kết quả
`already_active = 12`, không tạo dữ liệu trùng. Khi trang Quảng Ninh timeout ở
lần đầu, bộ nạp đã retry giới hạn và thành công ở lần hai; lỗi HTTP cố định vẫn
không được retry. Ma trận strict tăng lên 72/72 nguồn được phân loại, không có
blocker; số cây P0 giảm từ 23 xuống 16, số cây P1 tăng từ 60 lên 67, số ô có
bằng chứng phù hợp tăng từ 803 lên 833 và số ô gap giảm từ 3.724 xuống 3.682.

Benchmark 12 truy vấn đạt recall@1 = 100%, recall@3 = 100%, MRR = 100% và
nDCG@3 = 100%. Độ trễ trung bình là 8,36 giây nên đạt gate 10 giây. Một số truy
vấn đầu vẫn mất khoảng 14–20 giây do reranker CPU, vì vậy độ trễ đuôi tiếp tục
là điểm cần theo dõi dù toàn bộ gate của lô này đã đạt.

Các artefact kiểm toán gồm:

- `backend/eval/crop_data_expansion_batch_7_v1.json`
- `backend/eval/crop_data_expansion_batch_7_report.json`
- `backend/eval/retrieval_dataset_crop_expansion_batch_7_v1.json`
- `backend/eval/retrieval_baseline_crop_expansion_batch_7_v1.json`
- `backend/eval/retrieval_report_crop_expansion_batch_7_v1.json`

## Lô mở rộng rau và cây củ số 8

Lô `crop-data-expansion-batch-8-v1` bổ sung 17 tài liệu từ 16 nguồn cho toàn bộ
16 cây P0 còn lại: cải thìa, cải Brussels, cải cầu vồng, riềng, cải xoăn kale,
tỏi tây, sả, củ sen, đậu xanh, mùi tây, rau sam, dọc mùng, củ cải turnip,
xà lách xoong, khoai mỡ/khoai từ và bí ngòi. Tên tiếng Việt, tiếng Anh và tên
khoa học được thêm ở đầu từng lát để giảm nhầm giữa leek/hành lá,
turnip/radish, bok choy/cải thảo, riềng/gừng/nghệ và dọc mùng/khoai môn.

Các nguồn Utah State, Oregon State, UF/IFAS và University of Tennessee được
đánh dấu là hướng dẫn ngoài Việt Nam, không tự động chuyển lịch mùa vụ hoặc kết
quả vùng sang điều kiện trong nước. Dọc mùng dùng đúng loài `Colocasia gigantea`
và chỉ giữ bằng chứng nền cùng loài về đất, ánh sáng và chắn gió; không đồng nhất
với khoai môn `Colocasia esculenta` và không coi hướng dẫn cây cảnh là quy trình
sản xuất rau hoàn chỉnh. Nguồn tỏi tây không dùng tài liệu hành Paro
`Allium fistulosum`. Bản HTML của Oregon State được dùng thay PDF 41 MB nên không
cần nới giới hạn kích thước tải nguồn.

Các lát cắt kết thúc trước mục phân bón hoặc thuốc bảo vệ thực vật. Riêng rau sam
được tách thành hai tài liệu đất/ẩm và thu hoạch, loại cả hai khuyến nghị đạm định
lượng sau gieo và sau thu hoạch. Bảng mùi tây kết thúc trước danh sách thuốc đăng
ký; nguồn sen lấy củ kết thúc trước dinh dưỡng và quản lý dịch hại; nguồn đậu xanh
kết thúc trước chăm sóc, phân bón và phòng trừ sâu bệnh. Không hạ kiểm tra TLS và
không dùng các nguồn trả 403, 404 hoặc có chuỗi chứng thư không hợp lệ.

Đối soát sau ingest ghi nhận 17/17 tài liệu active, 19 chunk trong PostgreSQL và
19 point tương ứng trong Qdrant. Chạy lại manifest cho kết quả
`already_active = 17`, không tạo dữ liệu trùng. Ma trận strict đạt 88/88 nguồn
được phân loại, không có blocker và không còn cây P0; phân bố hiện tại là 83 cây
P1 và 8 cây P2. Số ô covered tăng từ 833 lên 836, gap giảm từ 3.682 xuống 3.676
và baseline-only tăng từ 13.321 lên 13.324 do ba ô được chuyển từ baseline sang
bằng chứng theo vùng/giai đoạn.

Sau khi thêm lớp xử lý phủ định tên cây, benchmark 17 truy vấn phân biệt cây dễ
nhầm đạt recall@1 = recall@3 = MRR = nDCG@3 = 100%. Câu mùi tây/rau mùi hiện đưa
tài liệu mùi tây đúng lên hạng 1 dù điểm cross-encoder thô của ngò rí cao hơn;
điểm thô vẫn được giữ để kiểm toán. Lần chạy hồi quy cuối có độ trễ trung bình
6,27 giây nên đạt gate 10 giây; truy vấn khởi động đầu tiên mất 20,40 giây, vì
vậy độ trễ lạnh của
reranker CPU vẫn cần theo dõi.

Các artefact kiểm toán gồm:

- `backend/eval/crop_data_expansion_batch_8_v1.json`
- `backend/eval/crop_data_expansion_batch_8_report.json`
- `backend/eval/retrieval_dataset_crop_expansion_batch_8_v1.json`
- `backend/eval/retrieval_baseline_crop_expansion_batch_8_v1.json`
- `backend/eval/retrieval_report_crop_expansion_batch_8_v1.json`

Sau lô này không mở thêm batch P0. Các lô kế tiếp phải đi theo khoảng trống P1 về
chủ đề, giai đoạn và vùng Việt Nam, ưu tiên nguồn chính thức trong nước và không
thêm tài liệu chỉ để tăng số lượng.

## Lô chiều sâu P1 số 9

Lô `crop-data-expansion-batch-9-v1` bổ sung 6 tài liệu được tách từ hai nguồn
Việt Nam của Trung tâm Khuyến nông Quốc gia. Năm lát của quy trình bí ngòi Star
Ol cho miền Bắc bao phủ riêng thời vụ/cây con, dinh dưỡng theo giai đoạn, mật
độ-độ ẩm-thụ phấn, IPM canh tác và thu hái. Lát sả ghi nhận trường hợp thích nghi
trên đất lúa cao cưỡng thiếu nước và mốc thu hoạch tại Nam Xuân, Nam Đàn, Nghệ
An; đây là bằng chứng vùng, không được suy rộng thành quy trình toàn quốc và
không đồng nhất sả gia vị với sả Java lấy tinh dầu.

Phần IPM bí ngòi giữ tên nhóm sâu bệnh, luân canh, vệ sinh, tưới hợp lý, giống
chống bệnh và che phủ. Khoảng văn bản chứa tên thuốc cũ cùng toàn bộ biện pháp
hóa học bị loại bằng marker range có kiểm tra fail-closed. Công cụ ingest cũng
chuẩn hóa timestamp có timezone về UTC-naive phù hợp schema hiện tại; test hồi
quy bảo đảm không tái phát lỗi ghi `published_date`.

Đối soát ghi nhận 6/6 tài liệu active, 8 chunk trong PostgreSQL và 8 point trong
Qdrant; chạy lại cho `already_active = 6`, không tạo trùng. Ma trận strict đạt
90/90 nguồn được phân loại, không có blocker; bí ngòi và sả chuyển từ P1 lên P2,
đưa phân bố thành 81 cây P1 và 10 cây P2. Số ô covered là 838, baseline-only là
13.342 và gap còn 3.656.

Benchmark đầu tiên cho thấy reranker nhận đúng cây nhưng đôi lúc xếp lát
mật độ/độ ẩm trên lát thời vụ hoặc dinh dưỡng. Lớp điều hướng chủ đề có giới hạn
đã được bổ sung cho các nhóm thời vụ/cây con, dinh dưỡng, nước/thụ phấn, IPM và
thu hoạch. Benchmark lại 8 truy vấn đạt recall@1 = recall@3 = MRR = nDCG@3 =
100%, độ trễ trung bình 5,83 giây và truy vấn lạnh đầu tiên 16,26 giây.

Các artefact kiểm toán gồm:

- `backend/eval/crop_data_expansion_batch_9_v1.json`
- `backend/eval/crop_data_expansion_batch_9_report.json`
- `backend/eval/retrieval_dataset_crop_expansion_batch_9_v1.json`
- `backend/eval/retrieval_baseline_crop_expansion_batch_9_v1.json`
- `backend/eval/retrieval_report_crop_expansion_batch_9_v1.json`

## Lô chiều sâu P1 số 10

Lô `crop-data-expansion-batch-10-v1` tách 6 lịch dinh dưỡng riêng cho cà chua,
dưa chuột, rau muống, mồng tơi, bắp cải và củ cải radish từ quy trình rau an
toàn phía Bắc của Trung tâm Khuyến nông Quốc gia. Mỗi lát giữ nguyên đơn vị trên
1 ha, có cảnh báo phải quy đổi theo diện tích và ghi rõ cặp cây dễ nhầm:
cà chua/cà tím, dưa chuột/bí ngòi, rau muống/cải bó xôi/mồng tơi, bắp cải/cải
thảo và radish/turnip. Nhờ vậy định lượng của một cây không bị gán sang cây bên
cạnh trong cùng bài nguồn.

Đối soát ghi nhận 6/6 tài liệu active, 6 chunk PostgreSQL và 6 point Qdrant;
chạy lại cho `already_active = 6`. Nguồn đã có trong registry nên tổng số nguồn
không đổi, nhưng cà chua, dưa chuột, rau muống, mồng tơi và radish chuyển từ P1
lên P2; bắp cải vốn đã ở P2. Ma trận sau lô này có 76 cây P1 và 15 cây P2.

Benchmark lạnh đạt recall@1 = recall@3 = MRR = nDCG@3 = 100%, nhưng độ trễ
trung bình 13,35 giây làm gate 10 giây không đạt; truy vấn đầu mất 28,71 giây.
Không hạ ngưỡng để che lỗi. Lượt đo ấm vẫn giữ toàn bộ chỉ số chính xác 100%,
độ trễ trung bình 6,50 giây và đạt gate.

Các artefact kiểm toán gồm:

- `backend/eval/crop_data_expansion_batch_10_v1.json`
- `backend/eval/crop_data_expansion_batch_10_report.json`
- `backend/eval/retrieval_dataset_crop_expansion_batch_10_v1.json`
- `backend/eval/retrieval_baseline_crop_expansion_batch_10_v1.json`
- `backend/eval/retrieval_report_crop_expansion_batch_10_v1.json`
- `backend/eval/retrieval_report_crop_expansion_batch_10_warm_v1.json`

## Lô chiều sâu P1 số 11

Lô `crop-data-expansion-batch-11-v1` bổ sung 8 lát từ ba quy trình Việt Nam cho
chuối, sắn và khoai tây. Chuối có lát nhận diện/đường lây bệnh héo vàng Panama
và lát IPM giống sạch, đất-nước, dinh dưỡng, vệ sinh, luân canh, sinh học. Sắn
có lát nhận diện/đường lây khảm lá, lát phòng bệnh không hóa học và lát quyết
định tiêu hủy theo tuổi cây cùng xử lý thân bệnh sau thu hoạch. Khoai tây vụ
đông miền Bắc có lát phân biệt sương mai, héo vàng, héo xanh, xoăn lá; lát IPM
canh tác; và lát thu hoạch-bảo quản.

Công cụ ingest được bổ sung `forbidden_terms` để fail-closed nếu nội dung sau
tách vẫn còn thuật ngữ thuốc cũ đã kiểm toán. Nhờ đó lát chuối loại xử lý giống
Bordeaux và mục hóa học; lát sắn dừng trước lịch phun; lát khoai tây dừng trước
danh sách thuốc cũ, gồm cả khuyến nghị pha nước rửa chén không an toàn. Tài liệu
khoai tây nguyên khối cũ được vô hiệu hóa mềm trong PostgreSQL và Qdrant sau khi
ba lát thay thế đã ingest và được xác minh; lịch sử vẫn được giữ để kiểm toán.

Đối soát ghi nhận 8/8 tài liệu active, 15 chunk PostgreSQL và 15 point Qdrant;
chạy lại cho `already_active = 8`. Cleanup chạy lại cho `already_inactive = 1`.
Ma trận strict đạt 92/92 nguồn, không có blocker; chuối và sắn chuyển từ P1 lên
P2, đưa phân bố thành 74 cây P1 và 17 cây P2. Số ô covered giữ ở 838,
baseline-only là 13.346 và gap giảm còn 3.652.

Benchmark 8 truy vấn phân biệt bệnh, cây dễ nhầm, giai đoạn xử lý và thu hoạch
đạt recall@1 = recall@3 = MRR = nDCG@3 = 100%. Lượt lạnh có độ trễ trung bình
12,37 giây nên chỉ trượt gate hiệu năng; truy vấn đầu mất 28,58 giây. Lượt đo ấm
đạt 8,32 giây và qua gate 10 giây mà không thay đổi ngưỡng.

Các artefact kiểm toán gồm:

- `backend/eval/crop_data_expansion_batch_11_v1.json`
- `backend/eval/crop_data_expansion_batch_11_report.json`
- `backend/eval/corpus_cleanup_legacy_potato_v1.json`
- `backend/eval/retrieval_dataset_crop_expansion_batch_11_v1.json`
- `backend/eval/retrieval_baseline_crop_expansion_batch_11_v1.json`
- `backend/eval/retrieval_report_crop_expansion_batch_11_v1.json`
- `backend/eval/retrieval_report_crop_expansion_batch_11_warm_v1.json`

## Lô chiều sâu P1 số 12

Lô `crop-data-expansion-batch-12-v1` bổ sung 5 lát từ ba nguồn Việt Nam. Một lát
sau thu hoạch quy mô HTX tại TP.HCM áp dụng đúng cho dưa leo, đậu bắp và khổ
qua, giữ các bước tránh chạm đất/dập, phân loại, bao bì thoáng và tạm trữ mát;
toàn bộ phần chlorine, ozone và xử lý hóa học ở trước đó bị loại. Hai lát măng
tây xanh từ Trung tâm Công nghệ Sinh học Đà Nẵng bao phủ cây con-xuống giống,
dinh dưỡng-nước và chu kỳ thu hoạch tại Hòa Vang; mục thuốc sâu bệnh bị loại.
Hai lát cà rốt Ninh Bình bao phủ thời vụ-đất-gieo-chăm sóc và nhận biết độ thu
hoạch-vận chuyển cho đồng bằng sông Hồng; đoạn thuốc hóa học không được lấy.

Đối soát ghi nhận 5/5 tài liệu active, 7 chunk PostgreSQL và 7 point Qdrant;
chạy lại cho `already_active = 5`. Ma trận strict đạt 95/95 nguồn, không có
blocker; măng tây, cà rốt, đậu bắp và khổ qua chuyển từ P1 lên P2, đưa phân bố
thành 70 cây P1 và 21 cây P2. Số ô covered tăng lên 844, baseline-only là
13.350 và gap giảm còn 3.642.

Benchmark 5 truy vấn đúng vùng, đúng giai đoạn và phân biệt măng tây/măng tre,
cà rốt/củ cải đạt recall@1 = recall@3 = MRR = nDCG@3 = 100%. Độ trễ trung bình
9,54 giây nên đạt gate 10 giây ngay trong lượt đo này; truy vấn đầu vẫn là điểm
đuôi chậm ở 18,47 giây.

Các artefact kiểm toán gồm:

- `backend/eval/crop_data_expansion_batch_12_v1.json`
- `backend/eval/crop_data_expansion_batch_12_report.json`
- `backend/eval/retrieval_dataset_crop_expansion_batch_12_v1.json`
- `backend/eval/retrieval_baseline_crop_expansion_batch_12_v1.json`
- `backend/eval/retrieval_report_crop_expansion_batch_12_v1.json`

## Lô chiều sâu P1 số 13

Lô `crop-data-expansion-batch-13-v1` bổ sung ba nguồn UF/IFAS Extension đã
khoanh vùng: bảng gieo trồng/thu hoạch cho 28 cây rau, lát thử nghiệm nhà kính
cho sáu rau gia vị, và lát nhận diện mùa vụ theo tên khoa học cho húng quế,
ngò rí và thì là. Mọi tài liệu đều ghi rõ dữ liệu Florida chỉ dùng đối chiếu,
không chuyển nguyên lịch vụ, khoảng cách hoặc năng suất sang Việt Nam. Bảng sản
phẩm bảo vệ thực vật bị loại bằng marker và `forbidden_terms`.

Đối soát ghi nhận 3/3 tài liệu active, 9 chunk PostgreSQL và 9 point Qdrant;
chạy lại cho `already_active = 3`. Ma trận strict đạt 98/98 nguồn, không có
blocker; 35 cây chuyển từ P1 lên P2, đưa phân bố thành 35 cây P1 và 56 cây P2.

Benchmark tám truy vấn cây dễ nhầm ban đầu phát hiện quy tắc tăng hạng theo tên
cây có thể lấn át một semantic match mạnh hơn nhiều. Quy tắc này đã được chặn
bởi khoảng điểm cạnh tranh tối đa 0,15 và có unit test hồi quy. Sau sửa,
recall@1 = recall@5 = MRR = 100%, nDCG@5 = 95,99%. Lượt cold giữ nguyên báo cáo
độ trễ 14,99 giây và trượt riêng cổng hiệu năng; lượt warm đạt 6,45 giây và qua
toàn bộ gate 10 giây.

Các artefact kiểm toán gồm:

- `backend/eval/crop_data_expansion_batch_13_v1.json`
- `backend/eval/crop_data_expansion_batch_13_report.json`
- `backend/eval/retrieval_dataset_crop_expansion_batch_13_v1.json`
- `backend/eval/retrieval_baseline_crop_expansion_batch_13_v1.json`
- `backend/eval/retrieval_report_crop_expansion_batch_13_v1.json`
- `backend/eval/retrieval_report_crop_expansion_batch_13_warm_v1.json`

## Lô chiều sâu P1 số 14

Lô `crop-data-expansion-batch-14-v1` bổ sung 9 lát từ sáu nguồn UF/IFAS cho
rau dền, cải thìa, bầu, mướp, đậu đũa, đậu rồng và đậu nành rau. Các lát được
cắt trước định lượng phân bón hoặc bảng thuốc; tên khoa học và cảnh báo cây dễ
nhầm được đặt trong nội dung. Registry đồng thời mở rộng nguồn gừng–riềng–nghệ
đã active cho đúng hai cây gừng và nghệ mà chính nguồn đó bao quát.

Đối soát ghi nhận 9/9 tài liệu active, 12 chunk PostgreSQL và 12 point Qdrant;
chạy lại cho `already_active = 9`. Ma trận strict đạt 104/104 nguồn, không có
blocker; phân bố còn 26 cây P1 và 65 cây P2.

Benchmark chín truy vấn ban đầu phát hiện tài liệu thu quả non đậu đũa đứng
hạng 27 dense và 36 BM25 nên không vào ba ứng viên rerank. Cửa sổ BM25 được mở
đến 50 nhưng trần reranker vẫn giữ ba; khâu chọn ứng viên dành chỗ cho tiêu đề
khớp cây được hỏi và có test hồi quy. Sau sửa, recall@1 = recall@5 = MRR = 100%,
nDCG@5 = 99,11%. Lượt cold trượt riêng độ trễ ở 11,91 giây; lượt warm đạt
6,19 giây và qua toàn bộ gate.

Các artefact kiểm toán gồm:

- `backend/eval/crop_data_expansion_batch_14_v1.json`
- `backend/eval/crop_data_expansion_batch_14_report.json`
- `backend/eval/retrieval_dataset_crop_expansion_batch_14_v1.json`
- `backend/eval/retrieval_baseline_crop_expansion_batch_14_v1.json`
- `backend/eval/retrieval_report_crop_expansion_batch_14_v1.json`
- `backend/eval/retrieval_report_crop_expansion_batch_14_warm_v1.json`

## Lô chiều sâu P1 số 15

Lô `crop-data-expansion-batch-15-v1` bổ sung 16 lát từ 11 nguồn đại học và cơ
quan nghiên cứu nông nghiệp cho 17 cây còn mỏng. Nội dung bao phủ atisô, tỏi,
ngò gai, diếp cá, củ đậu, thanh long, xoài, dứa, tần ô, tía tô, rau sam, cải
xoong, riềng, rau đay, khoai môn, rau răm và hồ tiêu đen. Các lát đều có tên
khoa học và cảnh báo cây dễ nhầm; bảng rau châu Á CV301 chỉ được dùng cho định
danh, còn tài liệu microgreen chỉ áp dụng cho giai đoạn rau mầm. Phần phân bón,
thuốc và nội dung ngoài lát đã bị loại bằng marker và `forbidden_terms`.

Đối soát ghi nhận 16/16 tài liệu active, 21 chunk PostgreSQL và 21 point Qdrant;
chạy lại cho `already_active = 16`. Ma trận strict đạt 115/115 nguồn, không có
blocker; phân bố tăng từ 65 lên 82 cây P2 và chỉ còn 9 cây P1.

Benchmark 16 truy vấn cây dễ nhầm, môi trường và thu hoạch đạt recall@1 =
recall@5 = MRR = 100%, nDCG@5 = 99,50%. Lượt lạnh đạt 6,64 giây và lượt ấm
đạt 5,44 giây; cả hai qua toàn bộ gate 10 giây.

Các artefact kiểm toán gồm manifest, report ingest, dataset/baseline retrieval
và hai report cold/warm mang hậu tố `crop_expansion_batch_15_v1`.

## Lô chiều sâu P1 số 16

Lô `crop-data-expansion-batch-16-v1` đóng chín cây cuối bằng 11 lát từ tám nguồn:
UC Davis và University of Miami cho rau ngót/lá lốt, NC State cho rau má,
Purdue cho đậu xanh/bí đao/sen củ, Clemson cho lạc, ICAR-IIPR cho giống đậu
xanh ngắn ngày, University of Guam cho các loài khoai mỡ-khoai từ và bảng Codex
do NC State IR-4 lưu trữ để định danh dọc mùng. Hai URL UGA trả 403 trong
pipeline đã bị loại hoàn toàn trước ingest và được thay bằng nguồn Clemson truy
cập ổn định. Bảng Codex chỉ là định danh hàng hóa, không phải hướng dẫn ăn sống,
canh tác hoặc dùng thuốc.

Đối soát ghi nhận 11/11 tài liệu active, 13 chunk PostgreSQL và 13 point Qdrant;
chạy lại cho `already_active = 11`. Ma trận strict đạt 123/123 nguồn active đã
phân loại, không có nguồn thiếu, thừa hoặc lệch loại. Kết quả cuối là 91/91 cây
P2, P1 = 0 và P0 = 0 mà không thay đổi công thức xếp hạng.

Benchmark 11 truy vấn nhóm cuối đạt recall@1 = recall@5 = MRR = nDCG@5 = 100%.
Lượt lạnh đạt 8,64 giây, lượt ấm đạt 6,68 giây; cả hai qua toàn bộ gate 10 giây.

Các artefact kiểm toán gồm manifest, report ingest, dataset/baseline retrieval
và hai report cold/warm mang hậu tố `crop_expansion_batch_16_v1`.

## Lô bằng chứng liên ngành số 17

Lô `crop-data-expansion-batch-17-v1` lấy ba lát đã kiểm toán từ hướng dẫn CGIAR
về đất, nước và IPM nông sinh thái. Pipeline dùng văn bản bitstream chính thức,
phân trang đầy đủ Qdrant và loại phần phương pháp hóa học khỏi lát IPM. Nguồn
quốc tế không được gán giả thành một vùng Việt Nam trong ma trận coverage.

## Lô chiều sâu cà chua số 18

Lô `crop-data-expansion-batch-18-v1` bổ sung tài liệu Trung tâm Khuyến nông Quốc
gia/Viện Bảo vệ thực vật về dấu hiệu sương mai, mốc lá, điều kiện ẩm và biện pháp
canh tác cà chua. Marker dừng trước phần hóa học; `forbidden_terms` xác nhận lát
ingest không chứa Ridomil, Mancozeb hoặc Fosetyl. Sau ingest, hai chunk của nguồn
mới đứng đầu truy hồi triệu chứng cà chua và giúp câu trả lời Vision có citation
truy vết thay vì bị guardrail chặn do thiếu bằng chứng.

Registry hiện có 125 URL nguồn duy nhất đã phân loại; nguồn CGIAR không nhận nhãn
vùng giả và nguồn cà chua dùng taxonomy stage/region hiện hữu.

## Lô cà chua đầu vụ số 19

Lô `crop-data-expansion-batch-19-v1` bổ sung một lát 3.217 ký tự từ Bản tin
Khuyến nông Việt Nam cho cà chua vụ đông miền Bắc: thời vụ, lựa chọn giống,
ươm cây, tiêu chuẩn cây xuất vườn, làm đất, mật độ và tưới hồi xanh. Số trang
PDF được kiểm tra bằng chính `pypdf`; lát dừng trước mục bón phân nên không lấy
liều phân hoặc thuốc BVTV. Đối soát ghi nhận 1 tài liệu active, 2 chunk ở cả
PostgreSQL và Qdrant.

## Lô đóng gap cây lâu năm số 20

Lô `crop-data-expansion-batch-20-v1` bổ sung bốn lát từ ba nguồn Việt Nam:
cải tạo đất/kiến thiết và quản lý hữu cơ cho cây có múi, cây giống/thời vụ xoài
VietGAP miền núi phía Bắc, và nguyên tắc dinh dưỡng hồ tiêu theo giai đoạn của
WASI. PDF hồ tiêu 25 MB ban đầu vượt trần ingest 15 MB nên bị loại; pipeline
không được nới giới hạn và dùng bài WASI 83 KB thay thế. Các lát dừng trước bảng
liều hoặc sản phẩm hóa học. Đối soát ghi nhận 4 tài liệu active, 7 chunk ở cả
PostgreSQL và Qdrant.

## Lô đóng topic gap cuối số 21

Lô `crop-data-expansion-batch-21-v1` bổ sung lát định lượng phân bón xoài năm
2023 của Trung tâm Khuyến nông Quốc gia và nguyên tắc phân hữu cơ cho dứa
Sugarloaf từ tài liệu do FAO đặt hàng. Liều xoài được đánh dấu phạm vi hẹp theo
giống, tuổi cây, đơn vị trên cây và vùng miền núi phía Bắc; phần Paclobutrazol,
KNO3 và thuốc BVTV không được ingest. Nguồn dứa chỉ dùng nguyên tắc hữu cơ ở
Ghana và không được gán vùng Việt Nam. Đối soát ghi nhận 2 tài liệu active, 2
chunk ở cả PostgreSQL và Qdrant.

Sau ba lô 19–21, ma trận strict đạt 130/130 nguồn active đã phân loại, không có
blocker và không còn `topic_gaps` trên 91 cây. Benchmark bảy truy vấn đạt
recall@1 = recall@5 = MRR = 100%, nDCG@5 = 97,71%. Hai lượt đều trượt riêng
gate hiệu năng: cold 15,51 giây và lượt đo lại 16,95 giây so với ngưỡng 10
giây; nguyên nhân cần tiếp tục theo dõi ở reranker CPU, không hạ ngưỡng để hợp
thức hóa kết quả.

## Lô tăng chiều sâu chuối, sắn và thanh long số 22

Lô `crop-data-expansion-batch-22-v1` bổ sung năm lát, tổng cộng 18.384 ký tự,
từ hai tài liệu do Cục Trồng trọt chủ trì: sổ tay chuối thích ứng biến đổi khí
hậu xuất bản năm 2021 và Quy trình thanh long bền vững, phát thải thấp ban hành
theo Quyết định 94/QĐ-TT-CCN ngày 24/02/2025. Các lát chỉ giữ thiết kế tưới,
chuẩn bị vườn theo địa hình, thu hoạch/sau thu hoạch chuối, cùng tưới, tỉa cành
quả và thu hoạch/vận chuyển thanh long. Phụ lục thuốc BVTV và bảng bón phân
không được ingest.

Đối soát ghi nhận 5 tài liệu active và 12 chunk tương ứng trong cả PostgreSQL
và Qdrant; chạy lại cho `already_active = 5`, không tạo trùng. Audit lại nguồn
sẵn có cũng chuyển nhãn giai đoạn từ `all` sang các giai đoạn được văn bản nêu
rõ cho chuối Ninh Bình, quy trình sắn bền vững và quản lý khảm lá sắn. Ma trận
strict đạt 132/132 nguồn active đã phân loại; số ô `covered` tăng từ 859 lên
1.029, `gap` giảm từ 3.606 xuống 3.597 và cả chuối, sắn, thanh long đều không
còn `stage_specific_gaps`. Các vùng không có bằng chứng địa phương vẫn giữ là
gap, không suy diễn nhãn `national` thành coverage vùng.

Benchmark warm chín truy vấn theo giai đoạn/vùng đạt recall@1 = recall@5 = MRR
= 100% và nDCG@5 = 99,64%. Gate chỉ trượt latency: trung bình 25,21 giây so với
ngưỡng 10 giây. Lượt cold trước đó đạt recall@1 88,89%, recall@5 100%, MRR
94,44%, nDCG@5 96,23% và latency 18,58 giây; kết quả top-1 bị xem là sai thực
ra là sổ tay thanh long cũ có đúng nội dung tỉa theo giai đoạn, đã được đọc trực
tiếp từ payload Qdrant và bổ sung vào nhãn relevance trước lượt warm.

## Quy tắc bổ sung có kiểm soát

1. Chọn lần lượt cây P1 trong backlog, ưu tiên cây phổ biến ở Việt Nam, cây người
   dùng thực tế đang canh tác và cây có nguồn chuyên biệt còn mỏng.
2. Tìm tài liệu theo các khoảng trống cụ thể trong `topic_gaps`, `stage_gaps`
   và `region_gaps`; không thu thập chỉ để tăng số lượng tài liệu.
3. Ưu tiên quy trình kỹ thuật từ cơ quan nhà nước/khuyến nông, sau đó là tổ chức
   nông nghiệp quốc tế. Chỉ dùng nghiên cứu khoa học cho khoảng trống chuyên sâu
   chưa được các nguồn trên bao phủ.
4. Kiểm tra quyền sử dụng, thời điểm, cây, vùng, giai đoạn, độ tin cậy và đơn vị
   trích dẫn trước khi ingest. Tài liệu hỗn hợp phải tách ở mức trang/chương để
   nguồn trích dẫn không gán sai cây.
5. Thêm nhãn nguồn vào registry, chạy ma trận ở chế độ `--strict`, rồi mới coi
   nguồn là hợp lệ. Nguồn mới chưa có nhãn khiến kiểm tra thất bại.
6. Sau ingest, chạy truy hồi mẫu và bộ đánh giá câu trả lời có dẫn nguồn. Chỉ
   đóng khoảng trống khi tài liệu đang active và được truy hồi đúng ngữ cảnh.

## Lệnh kiểm tra

Chạy từ thư mục `backend` trong container:

```powershell
python -m eval.build_crop_knowledge_matrix --strict
pytest -q tests/test_crop_knowledge_matrix.py tests/test_corpus_cleanup.py
```

`--strict` trả lỗi nếu có nguồn active chưa phân loại, nguồn đã đăng ký nhưng
không còn active, sai loại nguồn hoặc cùng một URL được gán nhiều loại. Báo cáo
được sinh lại từ trạng thái Postgres hiện tại nên backlog không phải danh sách
soạn tay.

## Dọn dữ liệu ngoài phạm vi

Manifest `backend/eval/corpus_cleanup_crop_scope_v1.json` ghi rõ từng tài liệu
mẫu, test hoặc chăn nuôi/thủy sản bị loại khỏi phạm vi cây trồng. Công cụ
`backend/eval/apply_corpus_cleanup.py` chỉ vô hiệu hóa mềm ở Postgres và Qdrant;
không xóa lịch sử. Có thể chạy không có `--apply` để đối soát an toàn trước khi
thay đổi dữ liệu.
