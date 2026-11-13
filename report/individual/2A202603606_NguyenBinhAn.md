# Báo cáo cá nhân — Lab Day 06

Học viên: **NguyenBinhAn — 2A202603606 — L3A** (theo tên repo được người dùng cung cấp; dấu tiếng Việt của họ tên: PENDING_USER).

Trạng thái: **PARTIAL — PENDING_HUMAN**. A/B/C đã chạy đủ; benchmark/retrieval metrics/trace và cấu hình được giữ nguyên. Người dùng đã xác nhận **30 coherence + 15 grounding**; điểm được tính từ từng nhãn, không suy ra từ text proxy. Nhãn score/evidence support là do người dùng duyệt; một số lý do trong CSV là AI đề xuất, **không coi là nhận xét do tác giả tự viết hoặc đã duyệt lý do**. Metadata 44 dòng và extraction/alternate gold vẫn PENDING_HUMAN. Chưa đủ điều kiện tuyên bố hoàn tất rubric hoặc nộp chính thức. Không push.

## Dữ liệu và pipeline

Corpus là trích đoạn tài liệu thiết kế KPI nội bộ, một nguồn `kpi-v2`. Có **42 trang vật lý, 42 trang nội dung**, gồm trang gốc **7–17 và 81–111**; **80,942 ký tự** sau chuẩn hóa. Kiểm tra riêng từng trang: không có bìa, mục lục, trang trống hoặc trang chỉ có tài liệu tham khảo; trang 111 là ma trận truy vết nguồn–thiết kế có nội dung nghiệp vụ. Không áp ngưỡng 1.500 ký tự của text không phân trang lên PDF.

SHA-256 PDF: `2a4801baffb2198686face4488c6f41b7dfa997bcc8260751170b436e2c72730`. Manifest chứa ánh xạ và số ký tự từng trang tại `data/manifest.json`. Quyền: người dùng xác nhận xử lý local, gửi chunk và 20 question text tới OpenRouter/Google ngày 13/11/2026; hai xác nhận được ghi riêng trong hồ sơ local. **Chưa có quyền tái phân phối** PDF, text, gold hoặc trace đầy đủ. Việc người chấm tiếp cận nguồn/benchmark còn PENDING_AUTHORIZED_ACCESS; số liệu tổng hợp không thay cho full trace.

RAW PDF → trích xuất từng trang → bỏ running header và nhãn trang lặp → Unicode NFC/whitespace, giữ line breaks → gán chapter và offsets → chunk A/B → embeddings API → PostgreSQL/pgvector → top-3 → proxy/nhãn review. `original_page` là page/gold_page chính thức; `pdf_page` là vị trí mở PDF rút gọn. Có khoảng trống trang 18–80 nên không lan metadata qua khoảng trống.

Parser chính pypdf 6.21.4; PyMuPDF 1.27.2.3 được dùng cho trang gốc **12, 13, 93** vì pypdf trả control characters trong công thức/cấu hình. Không tự viết lại công thức. Có **28 trang cảnh báo reading order bảng**, tổng **29 trang có ít nhất một cảnh báo**. Nội dung cảnh báo và body giữ local ở `.agents/processed/pages.jsonl`; manifest chỉ công bố loại cảnh báo/trang. Kiểm tra con người về thứ tự bảng: PENDING_HUMAN.

ID chunk là SHA-256 của document/page/cấu hình/offset/text/metadata nguồn. Upsert trong transaction với khóa bảng, xóa ID cũ không còn trong snapshot của từng tài liệu rồi ghi mới; lỗi count, vector chiều sai, nonfinite, filter ngoài allowlist chặn xử lý. Không có local embedding hoặc vector giả. Cache nằm local, khóa theo hash text + model + dimensions + encoding contract; C dùng chính dòng B. Ghi usage từng request thành công; timeout không tự gửi lại vì chưa biết đã bị tính phí hay chưa; 429/503 retry tối đa 3 lần, backoff hữu hạn.

## Model, backend và chi phí

- OpenRouter `POST /api/v1/embeddings`; `google/gemini-embedding-2`, **768 dimensions**, document và query cùng raw text, không task prefix khác nhau. Không dùng chat completions. Vector trả về được kiểm tra count/index/finite/chiều/nonzero. Giới hạn mỗi input là 8.192 byte UTF-8 bảo thủ; không giả định đã chạy tokenizer của model.
- PostgreSQL **16.16 (Debian 16.16-1.pgdg12+1)**, pgvector **0.8.7**, cosine `<=>`, **exact search**, không ANN. Docker image `pgvector/pgvector:0.8.7-pg16`, named volume `day6_nguyenbinhan_pg_data`; cổng local 55433. Bộ A/B lưu 306 dòng trong bảng `day06_chunks`; C ánh xạ B, không có index duplicate.
- Smoke test từ script có sẵn: thành công, **768 dimensions, 2 prompt tokens**, chỉ câu công khai. Phép thử này không phải benchmark.
- Pipeline usage đo được: **53406 prompt tokens**, **318 input**, **39 request batch thành công**. Provider trả `usage.cost` tổng **0.0106812 USD**. Giá tham chiếu kiểm tra 13/11/2026: 0,20 USD/triệu text tokens; ước tính từ usage là **0.0106812 USD**. Khoản này loại smoke test riêng 2 tokens; không thay cho đối soát hóa đơn tài khoản. Không ghi 0 cho chi phí chưa đo.
- API và thông số đối chiếu với [OpenRouter Embeddings](https://openrouter.ai/docs/api/api-reference/embeddings/submit-an-embedding-request), [model/pricing](https://openrouter.ai/google/gemini-embedding-2), [pgvector](https://github.com/pgvector/pgvector). Phiên bản package và thời điểm chạy ở `results/run_environment.json` nếu retrieval đã chạy.

## Metadata và ba cấu hình

Mỗi chunk có document_id/source/page, pdf_page/original_page, start/end, `section` kiểu string, heading provenance. `section` là chapter heading **thực trong nguồn**, truyền xuống các trang liên tiếp và cắt chunk tại chapter boundary; không suy đoán theo tên file hoặc gold. Corpus có **17 giá trị chapter**; không dùng year/version gần như hằng số để tạo lợi ích filter giả. Một số chapter chỉ xuất hiện một phần trong trích đoạn; metadata không cam kết chứa trọn chương.

| Cấu hình | Tham số | Số chunk | Min / median / max ký tự | Tổng ký tự |
|---|---|---:|---|---:|
| A | fixed 500 ký tự, overlap 50, giới hạn page/chapter | 202 | 50 / 500.0 / 500 | 88279 |
| B | paragraph/line packing tối đa 1.100 ký tự, word fallback, không overlap | 104 | 50 / 1010.5 / 1098 | 80880 |
| C | cùng chunk/vector với B; chỉ filter section theo input câu hỏi tại SQL | 104 (dùng B) | giống B | giống B |

A–B thay chính sách chunking (kích thước, overlap và boundary packing được nêu rõ); B–C chỉ đổi filter ở retrieval. Mọi cấu hình dùng cùng corpus, câu hỏi, model, dimensions, store, cosine và top-3. Bỏ whitespace ở mép chunk nên tổng ký tự B thấp hơn text trang; test bảo toàn mọi ký tự không phải whitespace đã kiểm tra.

## Benchmark và cách đánh giá

**20 câu, 15 dev/5 test**, gồm hỏi trực tiếp, paraphrase, điều kiện/ngoại lệ; **5 câu filter, 2 câu filter test**. AI soạn từ các trang thật trước retrieval, kiểm tra exact span của evidence và filter khớp chapter nguồn. **20/20 gold evidence chính đã được người dùng xác nhận ngày 2026-11-13**, lưu trong review overlay `.agents/review/gold_review.csv`. Các trường question/evidence/source/page và split của benchmark đã khóa không đổi. Các cờ human_verified=false trong benchmark/trace, manifest ban đầu và trạng thái PROVISIONAL_PENDING_HUMAN_GOLD trong metrics là snapshot trước xác nhận, được giữ nguyên; trạng thái review mới ở `results/human_review_summary.json`. Alternative gold cho cả 20 câu vẫn PENDING_HUMAN. Không thêm gold alternative hoặc tính lại retrieval metric khi chưa được duyệt.

Split theo chủ đề: dev phần quy tắc/quyền/yêu cầu/kiến trúc; test API conventions và vận hành/nghiệm thu. Một tài liệu dùng chung từ vựng, điều kiện có thể lặp; đây không phải holdout độc lập theo tài liệu. Không retune theo kết quả test. Question filter nói rõ chapter scope từ trước retrieval; A/B vẫn thấy cùng question text, C mới áp lọc SQL. Vì câu hỏi đã chứa ngữ cảnh chapter nên mức lợi ích filter có thể nhỏ.

Hash bộ benchmark trước retrieval: `62026ea23cbc82df48d3c410e6f6879050470df694d5de33fe9bc6eb2e39154c`; thời điểm lock `2026-11-13T09:34:32.417045+00:00`. Tiêu chí chọn đã khóa: **dev Evidence Hit@3 → dev Hit@1 → ít chunk lưu hơn → thứ tự strategy**. Lựa chọn được ghi trước test retrieval tại `.agents/results/selection_before_test.json`; lựa chọn tạm thời: **C**. Nhãn người dùng xác nhận sau thí nghiệm dùng để báo cáo, không dùng chọn lại cấu hình theo test.

Proxy kỹ thuật: cùng source_id/trang gốc và **toàn bộ evidence_quote** sau normalize whitespace nằm trong một chunk. Hit@1 = số top-1 hit/N; Evidence Hit@3 = số câu có ≥1 hit trong top-3/N. Các giá trị dưới đây giữ nguyên phép đo exact-quote ban đầu trên gold chính; alternative evidence chưa xác nhận nên chưa đánh giá đầy đủ các nguồn tương đương. Không suy retrieval hit từ điểm grounding người dùng và không tính lại các chỉ số sau merge xác nhận.

## Kết quả đo thật

| Strategy | Split | Hit@1, n/N (%) | Evidence Hit@3, n/N (%) |
|---|---|---|---|
| A | dev | 6/15 (40.0%) | 11/15 (73.3%) |
| A | test | 2/5 (40.0%) | 2/5 (40.0%) |
| B | dev | 7/15 (46.7%) | 12/15 (80.0%) |
| B | test | 2/5 (40.0%) | 3/5 (60.0%) |
| C | dev | 8/15 (53.3%) | 12/15 (80.0%) |
| C | test | 2/5 (40.0%) | 3/5 (60.0%) |

Ingest đầu tiên: A **19.544s**, B **10.078s** (gồm API/cache lookup và write đầu, không gồm setup/parser). B có 8 text trùng A đã được tái sử dụng; C không có lần gọi document embedding riêng. Write lại cùng vectors: A **0.184s**, B **0.104s**, count/IDs không đổi. Đây là một lần đo wall time, không phải benchmark hiệu năng nhiều lượt. Số đo search ở `results/search_timing.json`, gồm mở connection local; query embedding chia sẻ cùng một vector cho A/B/C.

Đã kiểm tra xóa stale chunk ID bằng một technical fixture từ chính chunk thật, sau đó khôi phục đầy đủ corpus trước retrieval. Chi tiết source-free ở `results/storage_verification.json`. Kiểm tra restart/persistence ở `results/persistence_verification.json` nếu có. Các phép thử kỹ thuật không được tính vào benchmark corpus hoặc usage token giả.

| Strategy | Coherence /2 (10 vị trí) | Metadata đủ/đúng (số bản ghi thực) | Filter compliance | Grounding /2 (5 câu) |
|---|---|---|---|---|
| A | 1.00 (n=10) | PENDING_HUMAN (15) | N/A (không áp lọc); quan sát scope 2/2 | 1.80; 0/1/2: 0/1/4 |
| B | 1.50 (n=10) | PENDING_HUMAN (15) | N/A (không áp lọc); quan sát scope 1/2 | 1.80; 0/1/2: 0/1/4 |
| C | 1.50 (n=10) | PENDING_HUMAN (14) | 2/2 scope trên hit thực; 1/2 đủ ba hit | 1.80; 0/1/2: 0/1/4 |

Coherence: cùng 10 vị trí nguồn trên 10 trang đầu, offset min(200, len−1), chọn chunk đầu tiên bao phủ vị trí. Grounding có đủ **5 câu test T01–T05 cho mỗi strategy**; T01=1, T02–T05=2 theo người dùng xác nhận, tổng 9/5=**1.80/2**, phân bố 0:0, 1:1, 2:4. Coherence A tổng 10/10=**1.00/2**, B/C tổng 15/10=**1.50/2**. Người dùng đã xác nhận **30 coherence + 15 grounding**; điểm được tính từ từng nhãn, không suy ra từ text proxy. Nhãn score/evidence support là do người dùng duyệt; một số lý do trong CSV là AI đề xuất, **không coi là nhận xét do tác giả tự viết hoặc đã duyệt lý do**. Metadata 44 dòng và extraction/alternate gold vẫn PENDING_HUMAN.

Metadata: mục tiêu tối đa 45 bản ghi test, thực nhận **44**. Có **89 mẫu có thể chấm**, cộng 1 dòng thiếu kết quả NOT_APPLICABLE. Trong đó đã duyệt **45 nhãn coherence/grounding**; 44 nhãn metadata còn chờ. C/T05 chỉ có 2 chunk B trong scope; không thêm hit giả. Filter scope trên hit thực nhận 2/2 query C; full-top-3 scope 1/2. Đối chiếu tự động source/trace: **44/44**, dòng PostgreSQL: **44/44**, nhưng **chưa công bố tỷ lệ metadata đúng/đủ do người chấm**. Review riêng: `.agents/review/metadata_review_44.csv`. Rủi ro thiên lệch do tự chấm và mẫu nhỏ vẫn có.

Trace đầy đủ (text, score, metadata, filters, gold, proxy từng câu) giữ local `.agents/results/traces.jsonl` (**60 dòng, 179 chunk records**; tối đa 180). Public repo chỉ có metrics tổng hợp, thống kê, hash và failure ID/trang; người chấm cần quyền riêng để xem nguồn/evidence. Không publish nội dung KPI để làm đủ checklist.

## Năm khía cạnh và phân tích

1. **Retrieval accuracy:** bảng trên giữ nguyên dev/test và số tử/mẫu. Test 5 câu: mỗi câu làm thay đổi 20 điểm phần trăm. Gold chính đã được xác nhận; việc tìm/duyệt evidence tương đương còn chờ, không tự sửa Hit@1/Hit@3.
2. **Chunk coherence:** Nhãn người dùng trên cùng 10 vị trí cho thấy A=1.00/2, B=C=1.50/2. Trong mẫu này B/C cao hơn A 0.50 điểm; chưa suy rộng ngoài 10 vị trí và không khẳng định xử lý trọn bảng qua nhiều trang.
3. **Metadata usefulness:** original_page/pdf_page giúp mở đúng trang nguồn; section giúp giới hạn phạm vi trong SQL. Hạn chế: chapter khá rộng, trích đoạn không liên tục và headings có thể bắt đầu giữa trang; scope sai sẽ loại evidence đúng. Mechanical compliance không chứng minh metadata đúng hay hữu ích về nghĩa.
4. **Grounding quality:** Người dùng xác nhận A=B=C=1.80/2 trên đủ 5 test, T01=1 và bốn câu còn lại=2. Đây là đánh giá độ đủ của top-3 evidence, không phải độ đúng câu trả lời LLM. Có thể khác exact-quote proxy vì xét ngữ cảnh và cách diễn đạt tương đương; xác nhận grounding không đồng nghĩa duyệt thêm alternative gold để tính lại retrieval.
5. **Data strategy impact:** A có 202 chunk, B có 104, giảm **48.5%** số dòng/vector; A thêm overlap nên tăng tổng ký tự được gửi. B lớn hơn dễ chứa cả điều kiện nhưng mỗi vector bao phủ nhiều ý. Dev Hit@3 B/C cùng 12/15, hơn A 11/15; C được chọn tạm thời vì dev Hit@1 8/15 so với B 7/15. Test B/C cùng Hit@3 3/5, A 2/5; không có bằng chứng từ mẫu test này cho thấy C tăng Hit@3 so với B. C loại hit ngoài scope ở T05 nhưng chỉ còn hai kết quả. Đọc kết quả cùng manual audit trước quyết định cuối, không thay tham số sau test.

Các case lỗi kỹ thuật đã chạy (nội dung nguồn giữ riêng):

- `D10`, strategy A, nguồn `kpi-v2`, trang gốc 17: top-3 tại [106, 17, 106]; `COMPLETE_QUOTE_NOT_IN_SINGLE_RETURNED_CHUNK`. Đây là lỗi theo proxy kỹ thuật; phải đọc trace riêng trước khi chốt thiếu evidence về nghĩa.
  Gold chiếm offsets [412, 533]; chunk trả về ở trang gold chiếm [[451, 740]]. Ranh giới cửa sổ làm mất một phần quote nên không được tính hit theo định nghĩa một chunk đủ evidence; không cộng nhiều chunk để thay metric chính.
- `D01`, strategy A, nguồn `kpi-v2`, trang gốc 7: top-3 tại [93, 106, 105]; `GOLD_PAGE_NOT_IN_TOP3`. Đây là lỗi theo proxy kỹ thuật; phải đọc trace riêng trước khi chốt thiếu evidence về nghĩa.
  Không trả về trang gold đã khai báo trong top-3; có thể do nội dung tương tự ở nhiều trang. Phải đối chiếu evidence tương đương trước khi kết luận là lỗi về nghĩa; không thêm alternate gold sau test để nâng số đo hiện tại.

Phân tích sâu và xác nhận alternative gold vẫn PENDING_HUMAN. Đã quét 20 quote trên 42 trang: không có quote giống hệt ở trang khác; 78 chunk ứng viên từ retrieval cũ được gom riêng cho 20 câu để người dùng xem, **chưa phải 78 gold hợp lệ**. Đã kiểm tra tự động 29 trang có cảnh báo; AI xem trực quan trang gốc 12,13,93,94, ghi nhận rủi ro bảng nối trang và sơ đồ raster không nằm đầy đủ trong plain text. Các nhận xét AI không xóa warning hoặc thay xác nhận người dùng. Không đổi processed text/chunk/embeddings/benchmark/trace; không retune hoặc chấm lại retrieval.

## Tái lập, giới hạn và việc còn chờ

Các lệnh và điều kiện dữ liệu ở README; tests chạy trên corpus thật/cache thật, không download embedding local. Source và benchmark không thể tái lập từ public checkout đơn lẻ khi chưa được cấp quyền; báo cáo công khai ghi rõ giới hạn này. Không giả định artifact tổng hợp đủ cho chấm full rubric.

PENDING: **44 metadata**, alternative gold cho 20 câu, xác nhận extraction/reading order, kiểm tra shortfall C/T05, tên có dấu, quyền người chấm truy cập nguồn và quyền công bố/push. Đã xác nhận 20 gold chính + 30 coherence + 15 grounding; không tiếp tục ghi các mục này là chờ duyệt. Số tổng hợp mới ở `results/human_review_summary.json` và `results/manual_evaluation_summary.csv`; file chấm chi tiết và gói xác nhận giữ local, không commit.

Công cụ hỗ trợ: Codex soạn code/câu hỏi/phân tích; OpenRouter chỉ tạo embedding. Người dùng phải hiểu code và tự xác minh evidence/nhãn. Không tạo dữ liệu, vector, kết quả, nguồn hoặc nhãn thủ công giả.
