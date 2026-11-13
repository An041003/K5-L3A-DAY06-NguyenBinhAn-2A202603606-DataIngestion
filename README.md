# Day 06 · Data Ingestion Engineering

**Lab cá nhân** · **4 giờ** · **Dữ liệu tự chọn**

Biến tài liệu thành kho tri thức có thể truy xuất cho AI agent, rồi đo xem cách chuẩn bị dữ liệu nào hiệu quả nhất.

| 📄 Dữ liệu | 🧩 Chiến lược | 🎯 Benchmark |
|---|---|---|
| Tối thiểu **30 trang nội dung** | Tối thiểu **3 cấu hình** | Tối thiểu **20 câu hỏi** |

## Bắt đầu nhanh

Dùng [starter PostgreSQL + pgvector](starter/README.md) để dựng database và hoàn thiện các hàm TODO, hoặc tự chọn vector store tương đương. Starter chỉ là khung: **bạn tự hiện thực pipeline và benchmark**.

## 1. Xây pipeline

![Đọc tài liệu, chuẩn hóa, chia chunk, tạo vector, lưu và kiểm tra](assets/ingestion-pipeline.svg)

Chọn tài liệu được phép sử dụng; giữ **ID tài liệu, nguồn, trang/vị trí** và metadata phù hợp. Dùng embedding model thật qua API hoặc chạy local; lưu và truy xuất bằng pgvector, Qdrant, Chroma hoặc một store tương đương.

## 2. So sánh và đánh giá

![Ba chiến lược được đánh giá trên cùng corpus và benchmark dev/test](assets/benchmark-workflow.svg)

Dùng cùng dữ liệu, model và câu hỏi cho cả ba cấu hình. Tách **15 câu dev / 5 câu test** trước khi chạy; chọn cấu hình trên dev, rồi đánh giá test sau khi cố định. Mỗi câu hỏi cần có đoạn bằng chứng và trang nguồn; thiết kế bộ câu hỏi và đánh giá theo [BENCHMARK.md](BENCHMARK.md).

Đánh giá theo năm khía cạnh: **độ chính xác truy xuất**, **tính mạch lạc của chunk**, **tính hữu dụng của metadata**, **chất lượng grounding** và **tác động của chiến lược dữ liệu**. Giải thích lựa chọn bằng kết quả, ví dụ lỗi và các đánh đổi.

## 3. Chuẩn bị bài nộp

1. Chạy pipeline và lưu cấu hình, kết quả top-3, trace cùng nhãn đánh giá thủ công.
2. Điền [thông tin học viên](STUDENT.md), [nhật ký thí nghiệm](artifacts/experiment_log.csv) và bản sao [mẫu báo cáo cá nhân](report/individual/MSSV_HoTen.md).
3. Kiểm tra mã nguồn, cách chạy, manifest dữ liệu và checklist trong [SUBMISSION.md](SUBMISSION.md).

## Tài liệu hướng dẫn

| Bạn cần tìm | Tài liệu |
|---|---|
| Setup baseline PostgreSQL + pgvector | [starter/README.md](starter/README.md) |
| Các bước làm và cách tính chỉ số | [GUIDE.md](GUIDE.md) |
| Tiến độ trong 4 giờ | [CHECKPOINTS.md](CHECKPOINTS.md) |
| Năm tiêu chí benchmark và bộ câu hỏi | [BENCHMARK.md](BENCHMARK.md) |
| Tiêu chí chấm điểm | [RUBRIC.md](RUBRIC.md) |
| Quy tắc sử dụng dữ liệu, AI và API | [RULES.md](RULES.md) |
| Cách nộp bài | [SUBMISSION.md](SUBMISSION.md) |

[data/format-example.json](data/format-example.json) chỉ minh họa định dạng, không phải corpus đủ điều kiện. Phần xử lý và benchmark do bạn tự hiện thực; không bắt buộc xây chatbot.

## Bài triển khai cá nhân — Nguyễn Bình An, 2A202603606, L3A

**READY cho hồ sơ local, với giới hạn công bố; chưa push/nộp.** OpenRouter `google/gemini-embedding-2`, 768 dimensions, PostgreSQL16 + pgvector, cosine exact. Không dùng local/mock embeddings.

- 20 gold chính, 30 coherence, 15 grounding: USER_CONFIRMED. Coherence A=1.00/2, B=C=1.50/2; grounding A=B=C1.80/2 trên đủ 5 test.
- Metadata:44/44 đối chiếu kỹ thuật được user chấp nhận, **USER_ACCEPTED_TECHNICAL_VERIFICATION**; A=15/15, B=15/15, C=14/14. Không tuyên bố người dùng tự chấm độc lập từng chunk. Khác biệt với phương pháp manual audit trong GUIDE được công bố, người chấm đánh giá mức rubric.
- Extraction: USER_ACCEPTED_WITH_DISCLOSED_LIMITATIONS; giữ 29 warning pages, 28 reading-order pages và fallback 12/13/93. Không coi29 trang đã human-verified hoặc extraction không lỗi.
- 78 candidate chunks chỉ định tính; không thêm alternative gold hoặc hồi tố metrics. D10/trang106 vẫn PENDING.

### Setup (PowerShell, từ repo root)

```powershell
python -m venv starter/.venv
starter/.venv/Scripts/python -m pip install -r starter/requirements.txt
if (!(Test-Path starter/.env)) { Copy-Item starter/.env.example starter/.env }
# Điền OPENROUTER_API_KEY trên máy; không dán vào Git/chat.
cd starter
docker compose -p day6_nguyenbinhan up -d --wait
.venv/Scripts/python scripts/check_setup.py
.venv/Scripts/python -m pip check
```

`.env.example` có DATABASE_URL local 127.0.0.1:55433; named volume day6_nguyenbinhan_pg_data. `check_setup.py` chỉ kiểm tra hạ tầng; thông báo gốc của utility không phản ánh tình trạng hoàn thiện pipeline. Không xóa volume để sửa setup. Dừng an toàn: `docker compose -p day6_nguyenbinhan stop`.

### Tái tạo báo cáo và kiểm chứng hiện tại

Nguồn KPI, page map, benchmark đã khóa và review được phép xem chỉ có local. Đọc [quyền/cách truy cập](data/ACCESS.md). Public checkout đơn lẻ không chứa corpus/questions/gold/text traces, nên không thể tái lập full benchmark mà chưa được cấp dữ liệu. Không dùng dữ liệu giả để thay thế.

Từ starter, **chỉ sinh lại báo cáo/số tổng hợp, không gọi API**:

```powershell
.venv/Scripts/python -m src.run report
```

Từ `starter/`, kiểm tra dữ liệu và số đo đã lưu, không chạy retrieval mới:

```powershell
.venv/Scripts/python -m src.submission
```

Từ repo root:

```powershell
starter/.venv/Scripts/python -m unittest discover -s tests -v
```

Các test cần source/cache/approvals thật sẽ skip khi thiếu; không dùng skip để nhận là đã kiểm chứng. `src.submission` cần hồ sơ private đầy đủ, thiếu sẽ báo BLOCKED, không tạo dữ liệu thay thế.

### Các lệnh của thí nghiệm đã thực hiện (không chạy lại trong final review)

Từ starter, trên dữ liệu được cấp quyền:

```powershell
.venv/Scripts/python -m src.run prepare
.venv/Scripts/python -m src.run lock
.venv/Scripts/python -m src.run ingest --allow-external
.venv/Scripts/python -m src.run benchmark --allow-external --allow-unverified
```

`--allow-external` chỉ sử dụng sau xác nhận quyền gửi chunk VÀ question text. `--allow-unverified` phản ánh trạng thái gold của lần chạy gốc. Không rerun benchmark chỉ để cập nhật approvals. Khóa kiểm tra hashes corpus/chunks/questions/config và vị trí audit. Chọn C bằng dev Hit@3→Hit@1→chunk count→strategy trước test; không retune bằng test. A=fixed 500/overlap 50; B=paragraph/line max 1100; C=dùng đúng chunk/vector B, thêm section filter khi có scope. Các câu không filter: C=B. C/T05 chỉ 2 eligible chunks nên rank 3 N/A, không tạo hit giả.

### Sản phẩm và lịch sử

- [Báo cáo cuối](report/individual/2A202603606_NguyenBinhAn.md), [STUDENT](STUDENT.md), [manifest](data/manifest.json), [benchmark manifest](benchmark/manifest.json), [experiment log](artifacts/experiment_log.csv).
- [Metrics dev/test](results/metrics.csv), [chunk stats](results/chunk_statistics.json), [ingest đầu](results/ingest_statistics.json), [ingest cache](results/ingest_latest.json), [search timing](results/search_timing.json), [usage/cost](results/api_usage_summary.json), [tài nguyên đo](results/resource_snapshot.json).
- [Human review hiện tại](results/human_review_summary.json), [bảng chất lượng](results/manual_evaluation_summary.csv), [submission readiness](results/submission_readiness.json).
- [Storage/idempotency](results/storage_verification.json), [persistence](results/persistence_verification.json), [rerun cũ](results/reproducibility.json), [failure summary](results/failure_summary.json), [runtime gốc](results/run_environment.json).

Benchmark/metrics/trace/manifest/experiment log gốc có cờ review PENDING lịch sử. Các byte thí nghiệm giữ nguyên; trạng thái hiện tại dùng human review summary và submission readiness. Không suy manual grounding thành retrieval hit hoặc thêm alternative chưa duyệt. Score người dùng và lý do AI đề xuất được tách provenance; giữ nguyên điểm/nhận xét approvals.

Dữ liệu nguồn, processed text, raw gold, full trace, file chấm và gói xác nhận vẫn local, không commit. Người chấm đã được user cho phép xem dữ liệu gốc; không suy ra quyền publish lên GitHub. Theo SUBMISSION.md, nguồn hạn chế dùng manifest/hướng dẫn truy cập và minh chứng an toàn. CờREADY nói về hồ sơ local, không có nghĩa đã push/nộp hoặc tự chấm đạt100 điểm.
