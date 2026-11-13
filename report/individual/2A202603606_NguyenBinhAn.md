# Báo cáo cá nhân — Day 06: Data Ingestion Engineering

**Nguyễn Bình An — 2A202603606 — L3A**

Repo: https://github.com/An041003/K5-L3A-DAY06-NguyenBinhAn-2A202603606-DataIngestion

**READY cho hồ sơ local, với giới hạn được công bố; chưa push/nộp GitHub.** Đã xác nhận 20 gold, 30 coherence, 15 grounding. Metadata là `USER_ACCEPTED_TECHNICAL_VERIFICATION`; extraction được chấp nhận với giới hạn. Không tự tuyên bố đạt 100/100 rubric: metadata được đối chiếu kỹ thuật rồi người dùng chấp nhận, khác phương pháp tự chấm độc lập từng chunk trong GUIDE; mức đáp ứng do người chấm quyết định.

## 1. Dữ liệu và pipeline

### 1.1. Corpus và quyền sử dụng

Một nguồn `kpi-v2`, tài liệu thiết kế KPI nội bộ: **42 trang PDF vật lý, 42 trang nội dung**, trang gốc **7–17 và 81–111**; **80,942 ký tự** sau clean. Kiểm tra từng trang theo GUIDE, loại bìa/mục lục/trang trống/tài liệu tham khảo đơn thuần; trang 111 là ma trận truy vết có nội dung. Không áp ngưỡng 1.500 ký tự của text không phân trang lên PDF.

SHA-256 PDF: `2a4801baffb2198686face4488c6f41b7dfa997bcc8260751170b436e2c72730`. Manifest giữ page map, ký tự, warnings và ngày truy cập của snapshot. Người dùng xác nhận quyền xử lý local, gửi chunk/question tới OpenRouter/Google và **người chấm được xem dữ liệu gốc**. Quyền xem riêng không bao gồm công bố PDF, processed text, gold hoặc trace hạn chế lên GitHub. `data/ACCESS.md` mô tả kiểm chứng riêng; public repo chỉ có code, manifest không body, số liệu tổng hợp và báo cáo. Không tự cấp quyền chia sẻ hoặc push.

### 1.2. Raw / Clean / Serve, parsing và normalization

**Raw:** PDF rút gọn và page_map giữ local; không upload PDF. Khoảng trang 18–80 không có trong excerpt, không tự điền nội dung thiếu.

**Clean:** pypdf 6.21.4 đọc từng trang; bỏ running title/nhãn trang lặp, Unicode NFC và whitespace normalization, giữ line breaks/page boundaries. Khi pypdf trả control characters tại trang gốc **12,13,93**, dùng PyMuPDF 1.27.2.3, ghi rõ fallback; không tự viết lại công thức.

**Serve:** chunk A/B theo page/chapter → HTTP embeddings thực → upsert PostgreSQL/pgvector → cosine exact top-k=3. C áp section filter trong SQL khi question cung cấp scope. Trace lưu text/score/metadata/proxy từng câu, chỉ local.

Người dùng **chấp nhận extraction với giới hạn**. Giữ nguyên **29 trang có warnings**, gồm **28 trang reading order bảng**, fallback **12,13,93**. Các loại warning giao nhau, không cộng 28+3 thành số trang khác nhau. Không chuyển 29 trang thành human_verified=true và không mô tả extraction hoàn toàn không lỗi. Bảng nối trang có thể thiếu ngữ cảnh; sơ đồ raster không hiện đầy đủ trong plain text. AI xem trực quan bốn trang 12/13/93/94 không thay kiểm tra toàn diện của người dùng.

### 1.3. Identity, metadata, lineage và quality gate

Page/chunk có document_id, source, page=original_page, pdf_page, offsets start/end, section và heading provenance. `pdf_page` mở bản 42 trang; `original_page` dùng gold/citation; ví dụ PDF page12 tương ứng trang gốc81. Section là chapter heading thật, truyền qua trang gốc liên tiếp, reset khi gap và cắt chunk tại chapter boundary. Có **17 chapter values**; không dùng year/version gần hằng số làm filter giả.

ID là SHA-256 của document/page/cấu hình/offset/text/metadata. Upsert transactional xóa stale IDs trong snapshot từng tài liệu rồi ghi lại; cùng input không tăng dòng. Đã kiểm tra re-ingestion, stale-ID removal/restore bằng technical fixture từ chunk thật và persistence sau restart Docker. Critical gate chặn thiếu nguồn/trang, sai vector/count/dimensions/finite values/model, thiếu key hoặc backend lỗi. Warning gate giữ cảnh báo parser/bảng, không tự điền text hoặc clear warning. Lineage: trace → chunk offsets → original_page/pdf_page → PDF đúng SHA.

### 1.4. Embedding và vector store

OpenRouter **google/gemini-embedding-2**, **768 dimensions**, POST `/api/v1/embeddings`. Query/document cùng encoding raw text, model và vector space; không chat completions, local embeddings hoặc mock. Kiểm tra index/count/order, finite/dimensions/nonzero. Batch tối đa 16 input, trần 8.192 byte UTF-8/input bảo thủ; không tự nhận đã chạy tokenizer model. Cache theo text hash/model/dimensions, retry 429/503 backoff hữu hạn; timeout không tự gửi lại khi chưa biết đã tính phí chưa. Không fallback provider.

Python 3.12.10; PostgreSQL **16.16 (Debian 16.16-1.pgdg12+1)**, pgvector **0.8.7**, cosine `<=>`, **exact search**, không ANN. Docker image pgvector/pgvector:0.8.7-pg16, cổng 127.0.0.1:55433, named volume day6_nguyenbinhan_pg_data. A 202 + B 104 = 306 rows; C ánh xạ B, không lưu thêm 104 vector. B tái sử dụng 8 text trùng A; C không gọi document embedding riêng. Key chỉ trong local .env/environment.

## 2. Cấu hình và benchmark

### 2.1. A/B/C và biến thay đổi

| Strategy | Chính sách | Chunk | Min / median / max ký tự | Tổng ký tự |
|---|---|---:|---|---:|
| A | fixed 500, overlap 50, giới hạn page/chapter |202|50 /500 /500|88279|
| B | paragraph/line packing, max 1100, word fallback, không overlap |104|50 /1010.5 /1098|80880|
| C | chính xác chunk/vector/DB rows B; section filter theo question |104 dùng B|giống B|giống B|

A–B thay chính sách chunking gồm size/overlap/packing, không quy kết riêng một yếu tố. B–C chỉ đổi filter. Giữ corpus, model, dimensions, store, cosine, question/gold, top-k. Không có scope thì C/B giống nhau cả IDs/score, đã test. Chỉ bỏ whitespace ở mép chunk; mọi ký tự không phải whitespace được kiểm tra bảo toàn.

### 2.2. Gold evidence và dev/test

**20 câu: 15 dev/5 test**, **5 filter queries, 2 thuộc test**. Có hỏi trực tiếp, paraphrase, điều kiện/ngoại lệ và phạm vi. Evidence là span nguồn thật; **20/20 gold chính đã được người dùng xác nhận**. Không đổi question/answer/split/source/evidence sau lock. Filter là scope có trong question/ngữ cảnh từ trước retrieval, không lấy gold source/page/answer làm query hoặc filter. A/B thấy cùng question, C mới lọc SQL.

Dev lấy chủ đề quy tắc/quyền/yêu cầu/kiến trúc, test lấy API conventions/vận hành/nghiệm thu. Vẫn có shared vocabulary và nội dung lặp, nên không gọi holdout độc lập theo tài liệu. Benchmark được soạn trước search; nhãn người dùng xác nhận sau đó không được dùng retune.

Hash benchmark `62026ea23cbc82df48d3c410e6f6879050470df694d5de33fe9bc6eb2e39154c`, lock UTC `2026-11-13T09:34:32.417045+00:00`. Tiêu chí khóa: **dev Hit@3 → dev Hit@1 → ít chunk → thứ tự strategy**. Đã chọn **C trước test retrieval**; giữ nguyên tới cuối, không chọn lại bằng test.

## 3. Kết quả

### 3.1. Retrieval Accuracy

Hit kỹ thuật cần đúng source/page và **toàn bộ evidence_quote** sau normalize whitespace trong một chunk. Hit@1=số top-1 hit / N; Evidence Hit@3=số câu có ít nhất 1 hit trong tối đa 3 chunk / N. Không ghép partial quotes để thay metric chính. Grounding score không tự xác nhận alternative gold.

| Strategy | Split | Hit@1 n/N (%) | Evidence Hit@3 n/N (%) | Chunk count |
|---|---|---|---|---:|
| A | dev | 6/15 (40.0%) | 11/15 (73.3%) | 202 |
| A | test | 2/5 (40.0%) | 2/5 (40.0%) | 202 |
| B | dev | 7/15 (46.7%) | 12/15 (80.0%) | 104 |
| B | test | 2/5 (40.0%) | 3/5 (60.0%) | 104 |
| C | dev | 8/15 (53.3%) | 12/15 (80.0%) | 104 |
| C | test | 2/5 (40.0%) | 3/5 (60.0%) | 104 |

**metrics.csv và trace giữ nguyên byte.** Cờ PROVISIONAL_PENDING_HUMAN_GOLD/human_verified=false ở snapshot ban đầu giữ cho lịch sử; quyết định hiện hành ở human_review_summary.json. Gold chính nay confirmed, nhưng proxy bảo thủ với diễn đạt/nguồn tương đương chưa duyệt. Không hồi tố nâng điểm.

### 3.2. Coherence, Metadata Usefulness và Grounding Quality

| Strategy | Coherence mean/2 (n) | Metadata kỹ thuật được chấp nhận | Filter compliance | Grounding 0/1/2; mean/2 (n) |
|---|---|---|---|---|
| A | 1.00 (10) | 15/15 | N/A; quan sát scope 2/2 | 0 / 1 / 4; 1.80 (5) |
| B | 1.50 (10) | 15/15 | N/A; quan sát scope 1/2 | 0 / 1 / 4; 1.80 (5) |
| C | 1.50 (10) | 14/14 | 2/2 hit trong scope; 1/2 đủ 3 hit | 0 / 1 / 4; 1.80 (5) |

**Coherence:** đủ 30 nhãn, cùng 10 vị trí đã khóa trước search; offset min(200,len−1) trên 10 trang đầu, lấy chunk có start nhỏ nhất bao phủ vị trí. Score 0/1/2 theo GUIDE. A tổng 10/10=1.00; B/C tổng 15/10=1.50. Giữ nguyên từng điểm và nhận xét gói approvals. Score user-confirmed; lý do AI đề xuất có provenance riêng, không gán tác giả tự viết/xác nhận lý do.

**Metadata:** người dùng chấp nhận **44/44**, **A=15/15, B=15/15, C=14/14**, đúng trạng thái **USER_ACCEPTED_TECHNICAL_VERIFICATION**. document_id/source/page/pdf_page/original_page/section và chunk text đã đối chiếu kỹ thuật với corpus, offsets, page map, heading provenance và SQL rows. **Không tuyên bố người dùng tự chấm độc lập từng chunk**; human_verified vẫn False. Khác biệt phương pháp với kiểm tra thủ công trong GUIDE được công bố để người chấm quyết định rubric. Lợi ích: truy đúng trang và loại hit ngoài scope. Hạn chế: chapter rộng, bảng nối trang, scope sai có thể loại evidence đúng; agreement DB/artifact không bảo đảm mọi quan hệ bảng đúng về nghĩa.

C có 2/2 filter test trong scope trên hit thực; chỉ 1/2 query đủ 3 hit. **C/T05 chỉ có 2 chunk B hợp lệ**, rank 3 NOT_RETURNED/NOT_APPLICABLE; chỉ 44 metadata, không duplicate hoặc tạo hit giả. A/B không filter nên compliance áp dụng là N/A; tỷ lệ quan sát trùng scope tương ứng 2/2 và 1/2 không phải bảo đảm lọc.

**Grounding:** đủ 15 nhãn, 5 test mỗi strategy. **T01:A=B=C=1; T02–T05:A=B=C=2**. Mỗi strategy 9/5=**1.80/2**, phân bố 0:0, 1:1, 2:4. Chấm độ đủ top-3 evidence, không phải độ đúng đáp án LLM. T05 có 2 hit vẫn 2/2 theo user-confirmed evidence sufficiency. Manual grounding khác exact-quote proxy không cho phép thêm alternative gold hoặc tính lại test.

### 3.3. Thời gian, tài nguyên và chi phí API

| Strategy | Ingest đầu s | Write lại s | Ingest cache s | Median SQL search ms/query |
|---|---:|---:|---:|---:|
| A | 19.544 | 0.184 | 0.329 | 21.57 |
| B | 10.078 | 0.104 | 0.179 | 19.21 |
| C | dùng B | dùng B | dùng B | 19.60 |

Ingest đầu gồm API/cache lookup+write đầu, không gồm setup/parser; search median từ 20 query gồm mở connection local, không gồm query embedding dùng chung A/B/C. C dùng ingest B, không có ingest riêng. Đây là một lượt wall time, không thử tải nhiều lượt hoặc kiểm định ý nghĩa thống kê latency.

202+104 vector, không thêm C; raw float32 payload lý thuyết 306×768×4=**940.032 byte**, chưa overhead. Đo read-only cuối: 306 dòng; bảng và index PostgreSQL chiếm 5,070,848 byte, gồm text/metadata/vector/index. CPU/RAM/GPU peak chưa đo; không báo số giả. Không chạy local model hoặc tác vụ GPU embedding trên máy client. Cache làm lượt sau nhanh hơn; không coi cold/warm là cùng điều kiện.

Pipeline usage **53,406 prompt tokens**, **318 input**, **39 batch thành công**; provider trả usage.cost tổng **0.0106812 USD**. Giá tham chiếu 0,20 USD/triệu text tokens, kiểm tra 13/11/2026, cho estimate 0.0106812 USD; không thay đối soát hóa đơn. Smoke script gửi câu công khai, trả 768 chiều/2 tokens; tổng pipeline loại 2 tokens này. Final review không gọi embedding hoặc benchmark lại. Không ghi 0 cho chi phí chưa đo.

Nguồn kỹ thuật: [OpenRouter embeddings](https://openrouter.ai/docs/api/api-reference/embeddings/submit-an-embedding-request), [model/pricing](https://openrouter.ai/google/gemini-embedding-2), [pgvector cosine](https://github.com/pgvector/pgvector). Giá/versions là snapshot thí nghiệm, không cam kết giá tương lai.

## 4. Phân tích và kết luận

### 4.1. Data Strategy Impact và failures

A–B giảm 202→104 chunk (**48,5%**), ký tự 88279→80880 do bỏ overlap; coherence trong mẫu 1.00→1.50. Dev Hit@3 tăng 11/15→12/15; test 2/5→3/5. Đổi cả policy nên chưa tách tác động size và overlap. Chunk B nhiều ý hơn mỗi vector, vẫn có thể mất ngữ cảnh bảng nhiều trang.

B–C cùng vectors, filter nâng dev Hit@1 từ 7/15→8/15; dev Hit@3 cùng 12/15. Test cùng Hit@1=2/5, Hit@3=3/5; coherence cùng 1.50, grounding cùng 1.80. **Không khẳng định C tốt hơn B trên test.** C giữ scope nhưng có thể thiếu slot top3 như T05, chỉ áp khi scope input đáng tin.

- **D10, A, kpi-v2/trang gốc 17:** gold offsets 412–533; top-3 trang[106,17,106]. Chunk trang 17 ở 451–740 thiếu đầu quote; các cửa sổ 500/overlap 50 không chứa toàn bộ quote trong một chunk. Trang 106 có nội dung gần nhưng **D10/trang106 vẫn PENDING**, chưa được user xác nhận riêng, không thêm gold hay sửa hit.
- **D01, A, kpi-v2/trang gốc 7:** top-3 trang[93,106,105], không có trang 7 gold. Có nội dung liên quan ở trang khác nên cần phân biệt retrieval miss và thiếu alternate annotation; chưa đủ approval để gọi hit. Giữ nguyên lỗi proxy, chỉ phân tích định tính.

Hai case có trace thật; không công bố question/evidence nguyên văn. IDs/pages/offsets ở failure_summary.json. Rủi ro boundary và nhãn exact-quote không chứng minh mọi hit ngoài gold đều sai về nghĩa.

### 4.2. Giới hạn và khả năng tái lập

**78 chunk ứng viên chỉ phân tích định tính**; không thêm vào gold chính thức hoặc hồi tố test. D10/trang106 còn PENDING là giới hạn được công bố, không chặn nộp phép đo đã khóa. Test 5 câu: một câu tương ứng 20 điểm phần trăm; cùng tài liệu/người chấm có nguy cơ thiên lệch, không suy rộng chiến lược tốt nhất tổng quát.

Extraction được chấp nhận với 29 warnings giữ nguyên; bảng nối trang, reading order, raster và fallback còn giới hạn. Metadata là technical verification được user chấp nhận, không phải independent manual audit. **Public checkout đơn lẻ không tái lập full benchmark** do nguồn hạn chế. Người chấm được xem nguồn theo quyền riêng, đối chiếu trực tiếp local theo data/ACCESS.md; không tự upload/gửi dữ liệu cho bên khác.

Manifest/benchmark/experiment_log/results gốc giữ các cờ review lịch sử trước khi user chấp nhận; human_review_summary.json, manual_evaluation_summary.csv và submission_readiness.json ghi kết luận hiện hành. Source/gold/traces/file chấm/gói approvals giữ local, không commit. Không suy ra extraction không lỗi hoặc quyền công bố từ quyết định chấp nhận pipeline.

### 4.3. Lựa chọn chiến lược và việc cải tiến

**Giữ C theo tiêu chí dev đã khóa**, không chọn lại theo test. B/C có cùng test và grounding; C phù hợp scope input hợp lệ, B dùng chính vectors đó khi không có scope. Chấp nhận trade-off độ phủ sau lọc và slot N/A. Nếu mở rộng: thử paragraph/table-aware extraction trên dev trong thí nghiệm mới, thêm source context, holdout mới lớn hơn; giữ lịch sử hiện tại.

User-confirmed: 20 gold, 30 coherence, 15 grounding. User-accepted technical: 44 metadata. User-accepted with limits: extraction 29 warning pages. Chưa xác nhận riêng: D10/trang106 và alternative candidates, chỉ định tính. Codex hỗ trợ code/câu hỏi/phân tích; OpenRouter chỉ embeddings. Phân biệt score người dùng và nhận xét AI; không tạo dữ liệu/vector/nhãn/chi phí giả.

Hồ sơ **READY cho nộp local với giới hạn và quyền hợp lệ**, chưa push. Khác biệt metadata technical verification so với manual audit do người chấm đánh giá rubric. Quyền công bố dữ liệu nội bộ và push chưa được cấp.
