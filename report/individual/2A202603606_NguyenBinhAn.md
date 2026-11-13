# Báo cáo cá nhân — Day 6

## Dữ liệu và pipeline

- Chủ đề, nguồn/quyền, số trang và quy tắc tính trang: Tài liệu thiết kế KPI nội bộ, nguồn `kpi-v2`, 42 trang nội dung (trang gốc 7–17 và 81–111); loại bìa, mục lục, trang trống và trang chỉ có tài liệu tham khảo. Được phép xử lý và cho người chấm xem riêng; không công bố corpus, gold hoặc full trace. Nguồn và cách truy cập: `data/manifest.json`, `data/ACCESS.md`.
- Chuẩn hóa, lỗi và giới hạn: PDF → trích xuất từng trang → Unicode NFC, chuẩn hóa whitespace → chunk → embedding → pgvector. Dùng pypdf 6.21.4, fallback PyMuPDF 1.27.2.3 tại trang 12, 13, 93. Giữ 29 trang có cảnh báo, gồm 28 trang reading order bảng. Extraction được chấp nhận với giới hạn; chưa kiểm tra toàn diện từng trang, không coi là hoàn toàn không lỗi.
- Embedding model/provider/version/số chiều, vector store/version, metric, lệnh chạy và chi phí: OpenRouter `google/gemini-embedding-2`, 768 dimensions; PostgreSQL 16.16 + pgvector 0.8.7, cosine exact. Chạy từ `starter/`: `python -m src.run ingest --allow-external` và `python -m src.run benchmark --allow-external --allow-unverified` (lệnh thí nghiệm đã thực hiện). Tổng API: 53,406 tokens, **0.0106812 USD**, dùng chung A/B/C; không phân bổ riêng theo split. Nạp lại không tăng số dòng; dữ liệu tồn tại sau restart DB.
- Metadata bắt buộc, trường lọc bổ sung, nguồn giá trị và lý do chọn: `document_id`, `source`, `page=original_page`, `pdf_page`, offsets và `section`. Section lấy từ chapter heading thật để lọc phạm vi; page map dùng truy đúng trang nguồn. Chunk ID theo hash, giữ lineage tới source spans và kiểm tra dimension/nguồn/trang trước khi lưu.

## Cấu hình và benchmark

- A / B / C (tham số cụ thể, khác biệt duy nhất B–C): A fixed 500 ký tự, overlap 50, 202 chunk; B paragraph/line tối đa 1.100 ký tự, không overlap, 104 chunk. C dùng chính chunk/vector B, chỉ thêm section filter khi question cung cấp scope. Cùng corpus, model, dimensions, backend và cosine.
- ≥20 câu: phân chia ≥15 dev / ≥5 test, câu metadata filter và cách kiểm chứng evidence: 20 câu (15 dev/5 test), 5 câu filter, gồm 2 test. Đã đối chiếu evidence với trang nguồn và người dùng xác nhận 20/20 gold chính. Giữ nguyên benchmark; hit yêu cầu đúng source/page và chứa toàn bộ quote trong một chunk.
- Tiêu chí chọn chiến lược đã chốt trước khi xem test: Dev Evidence Hit@3 → Hit@1 → ít chunk → thứ tự strategy; đã chọn C trước test. Không chỉnh cấu hình theo test.

## Kết quả

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---|---|---|---|---|---|
| A | dev | 6/15 | 11/15 | 202 | 19.544 s ingest | Dùng chung |
| A | test | 2/5 | 2/5 | 202 | 19.544 s ingest | Dùng chung |
| B | dev | 7/15 | 12/15 | 104 | 10.078 s ingest | Dùng chung |
| B | test | 2/5 | 3/5 | 104 | 10.078 s ingest | Dùng chung |
| C | dev | 8/15 | 12/15 | 104 | Dùng B | Dùng chung |
| C | test | 2/5 | 3/5 | 104 | Dùng B | Dùng chung |

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| A | 1.00 (10) | 15/15 | N/A; quan sát scope 2/2 | 0 / 1 / 4; 1.80 (5) |
| B | 1.50 (10) | 15/15 | N/A; quan sát scope 1/2 | 0 / 1 / 4; 1.80 (5) |
| C | 1.50 (10) | 14/14 | 2/2 hit trong scope; 1/2 đủ 3 hit | 0 / 1 / 4; 1.80 (5) |

Đường dẫn trace, nhãn thủ công và cách chọn mẫu: `.agents/results/traces.jsonl`, `.agents/review/manual_audit_template.csv`; số tổng hợp tại `results/metrics.csv`, `results/manual_evaluation_summary.csv`. Coherence: cùng 10 vị trí nguồn đã khóa trước search, đủ 30 nhãn xác nhận. Grounding: đủ 5 test/strategy, T01=1, T02–T05=2; giữ nguyên điểm và nhận xét đã có. Metadata 44/44 là **USER_ACCEPTED_TECHNICAL_VERIFICATION**, không phải người dùng tự chấm độc lập từng chunk. C/T05 chỉ có 2 hit hợp lệ: rank 3 N/A; scope tuân thủ 2/2 query nhưng chỉ 1/2 query đủ 3 hit. Thời gian trong bảng là ingest dùng cho cả hai split, không cộng hai lần.

## Phân tích và kết luận

- So sánh A–B và B–C; 2 ví dụ sai có ID câu và nguồn: B giảm 202→104 chunk, coherence tăng 1.00→1.50; test Hit@3 tăng 2/5→3/5 so với A. C tăng dev Hit@1 từ 7/15→8/15 so với B, nhưng test B/C giống nhau. D10/A, `kpi-v2` trang 17: chunk trả về thiếu đầu quote; D10/trang106 đã được xác nhận là bằng chứng tương đương, nhưng không thêm vào gold hoặc tính lại metric. D01/A, `kpi-v2` trang 7: top-3 tại trang 93/106/105, không có trang gold nên không tính hit.
- Chiến lược chọn, đánh đổi, điều kiện áp dụng: Giữ C theo tiêu chí dev; dùng khi scope đáng tin, không có scope thì tương đương B. Filter có thể giảm số kết quả; không khẳng định C tốt hơn B trên test.
- Hạn chế của dữ liệu, nhãn, test nhỏ, đo thời gian/chi phí: Một tài liệu, chỉ 5 test, có nội dung lặp; metadata là kiểm chứng kỹ thuật được chấp nhận, khác manual audit độc lập. Giữ 29 cảnh báo extraction; 78 candidate chunks chỉ định tính, không hồi tố test. Thời gian đo một lượt, không kiểm định thống kê; chi phí là provider-reported usage. Public checkout không chứa dữ liệu hạn chế nên cần quyền xem riêng để kiểm chứng.
- Nếu làm lại hoặc mở rộng, cải tiến gì? Thử chunking nhận biết bảng/đoạn, giữ ngữ cảnh bảng nối trang; bổ sung gold thay thế sau xác minh và đánh giá trên holdout mới lớn hơn. Không thay đổi phép đo đã khóa hiện tại.
