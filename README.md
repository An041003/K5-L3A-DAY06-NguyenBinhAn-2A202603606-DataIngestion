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

Python + OpenRouter `google/gemini-embedding-2`, **768 dimensions** + PostgreSQL 16/pgvector, cosine exact search. A: fixed 500/overlap 50; B: paragraph/line tối đa 1.100 ký tự; C: dùng cùng chunk/vector B, thêm section filter do câu hỏi cung cấp. Không có local/mock embeddings. Trạng thái: **PARTIAL**; đã xác nhận 20 gold chính, 30 coherence và 15 grounding; còn 44 metadata, alternative gold và extraction chờ duyệt.

### Cài đặt và chạy

Từ repo root, trên Windows PowerShell:

```powershell
python -m venv starter/.venv
starter/.venv/Scripts/python -m pip install -r starter/requirements.txt
# Chỉ copy nếu chưa có .env; điền key thật trực tiếp trên máy, không đưa vào Git.
if (!(Test-Path starter/.env)) { Copy-Item starter/.env.example starter/.env }
cd starter
docker compose -p day6_nguyenbinhan up -d --wait
.venv/Scripts/python scripts/check_setup.py
```

`starter/.env` dùng DATABASE_URL của `.env.example`, OPENROUTER_API_KEY local, model/dimensions như trên. `check_setup.py` chỉ kiểm tra hạ tầng, không phải benchmark. Docker dùng volume riêng `day6_nguyenbinhan_pg_data`, bind `127.0.0.1:55433`. Không xóa volume để xử lý lỗi setup. Dừng bằng `docker compose -p day6_nguyenbinhan stop`.

Corpus KPI là **dữ liệu nội bộ không được phép công bố**. Người được cấp quyền phải chuẩn bị đúng PDF 42 trang và page map theo [manifest](data/manifest.json), cùng benchmark đã khóa. Các file này có sẵn local trong `.agents/corpus/` và `.agents/benchmark/`; public checkout không chứa chúng. Liên hệ tác giả để được đơn vị cho phép truy cập; không có URL tải công khai. Không thể tái lập full benchmark từ public checkout đơn lẻ.

Người dùng đã xác nhận **người chấm được xem dữ liệu gốc** để kiểm chứng bài. Đây là quyền xem riêng, chưa cho phép công bố corpus trên GitHub.

Từ `starter/`, chạy từng bước:

```powershell
.venv/Scripts/python -m src.run prepare
.venv/Scripts/python -m src.run lock
# Chỉ dùng --allow-external khi có quyền gửi chunk VÀ question text tới provider.
.venv/Scripts/python -m src.run ingest --allow-external
# Lần benchmark ban đầu dùng gold chưa duyệt; cờ của snapshot đó được giữ nguyên.
.venv/Scripts/python -m src.run benchmark --allow-external --allow-unverified
.venv/Scripts/python -m src.run report
```

Sau khi các đầu vào đã được cấp quyền và có benchmark local, lệnh tổng hợp tương đương:

```powershell
.venv/Scripts/python -m src.run --allow-external --allow-unverified
```

Model/dimensions/cosine được giữ cố định. Lock kiểm tra hash câu hỏi, cấu hình, chunks và vị trí audit; không sửa để retune test. Dev chọn theo Evidence Hit@3, rồi Hit@1, số chunk, thứ tự strategy; ghi lựa chọn trước test retrieval. Cache local tái sử dụng text trùng và query vectors; C không gọi embedding document riêng. Timeout/401/402/quota/backend lỗi sẽ báo rõ và dừng bước phụ thuộc, không chuyển provider.

Các lệnh ingest/benchmark ở trên mô tả lần chạy thí nghiệm. **Sau khi merge nhãn người dùng, chỉ chạy `python -m src.run report` từ starter để cập nhật báo cáo**, không chạy lại benchmark để cập nhật review. Gói xác nhận và CSV chấm nằm local trong `.agents/review/`; reporter đối chiếu JSON/CSV theo ID/strategy, tính lại số tổng hợp và giữ nguyên benchmark/trace/metrics. Các cờ review cũ trong snapshot thí nghiệm không phản ánh trạng thái xác nhận mới.

### Kết quả và kiểm chứng

- [Báo cáo cá nhân](report/individual/2A202603606_NguyenBinhAn.md): cấu hình, phép đo, năm khía cạnh, ví dụ lỗi và giới hạn.
- [Metrics dev/test](results/metrics.csv), [chunk statistics](results/chunk_statistics.json), [ingest statistics](results/ingest_statistics.json), [API usage](results/api_usage_summary.json), [experiment log](artifacts/experiment_log.csv).
- [Backend verification](results/storage_verification.json), [persistence sau restart](results/persistence_verification.json), [runtime](results/run_environment.json), [failure summary](results/failure_summary.json), [search timing](results/search_timing.json).
- Trace đầy đủ local: `.agents/results/traces.jsonl`; draft gold/review: `.agents/review/gold_review.csv`; 89 mẫu coherence/metadata/grounding và 1 dòng thiếu kết quả: `.agents/review/manual_audit_template.csv`. C/T05 chỉ có 2 chunk thuộc phạm vi lọc, tổng 60 trace có 179 kết quả thực; không tạo hit thứ ba. Không có nhãn người chấm được AI tự điền; chưa commit nguồn, câu hỏi/gold hoặc text trace.
- [Benchmark manifest](benchmark/manifest.json) ghi split/hash và phạm vi review; [rerun verification](results/reproducibility.json) ghi kiểm tra kết quả lần chạy lại. `ingest_statistics.json` giữ phép đo ingest đầu tiên; `ingest_latest.json` ghi lần nạp lại bằng cache.
- [Human review hiện tại](results/human_review_summary.json) và [bảng manual evaluation](results/manual_evaluation_summary.csv): coherence A=1.00/2, B=C=1.50/2 (10 vị trí mỗi cấu hình); grounding A=B=C=1.80/2 (đủ 5 test). Điểm do người dùng xác nhận; lý do AI đề xuất không được gán thành nhận xét do tác giả viết. File chấm chi tiết không được công bố.

`Hit@1`/`Evidence Hit@3` giữ nguyên **exact-quote proxy của thí nghiệm ban đầu**: phải đúng nguồn/trang và chứa toàn bộ quote trong một chunk. Nay 20 gold evidence chính đã được người dùng xác nhận, còn alternative gold chưa duyệt nên không tự thêm nguồn tương đương hoặc tính lại metric. Cờ PENDING trong metrics/benchmark manifest/trace là lịch sử trước xác nhận; review mới được lưu riêng trong human review summary. Metadata filter compliance tự động không chứng minh độ đúng metadata thủ công.

Chạy technical tests từ repo root (đọc corpus/cache thật, không gọi API):

```powershell
starter/.venv/Scripts/python -m unittest discover -s tests -v
```

Các test cần dữ liệu nội bộ sẽ báo skip nếu checkout chưa được cấp corpus/cache. Không dùng việc skip để tuyên bố pipeline đã được kiểm chứng. Thông số API và giá tham chiếu: [OpenRouter endpoint](https://openrouter.ai/docs/api/api-reference/embeddings/submit-an-embedding-request), [model](https://openrouter.ai/google/gemini-embedding-2); SQL metric theo [pgvector](https://github.com/pgvector/pgvector).
