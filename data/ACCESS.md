# Quyền truy cập và cách kiểm chứng nguồn hạn chế

Nguyễn Bình An, MSSV 2A202603606, L3A xác nhận người chấm được xem dữ liệu gốc. Corpus KPI là tài liệu nội bộ; quyền xem riêng không cấp quyền đưa PDF, processed text, câu hỏi/gold, full trace, file chấm hoặc gói approvals lên GitHub. Không có URL tải công khai, không tự gửi/upload cho bên khác.

Public repo có `manifest.json` (không body), benchmark manifest, code, số tổng hợp và báo cáo. Benchmark/manifest/metrics/experiment log gốc giữ trạng thái lịch sử trước xác nhận; quyết định review hiện hành nằm trong `results/human_review_summary.json` và `results/submission_readiness.json`.

Người chấm liên hệ tác giả để kiểm chứng trực tiếp trên máy chứa corpus, trong phạm vi quyền truy cập hợp lệ. Không cần cấp hoặc nhìn API key, không cần gọi API để đọc chứng cứ:

1. Mở PDF local `.agents/corpus/kpi_ooad_uml_selected_42p_PRIVATE.pdf`; kiểm tra SHA-256 khớp `manifest.json` bằng `Get-FileHash -Algorithm SHA256 <đường_dẫn_PDF>`.
2. Dùng `.agents/corpus/page_map.csv`: `original_page` là trang nguồn dùng trong gold/trace; `pdf_page` là vị trí mở PDF rút gọn. PDF page12 ứng với trang gốc81.
3. Tác giả đối chiếu câu hỏi/gold ở `.agents/benchmark/questions.jsonl`, kết quả ở `.agents/results/traces.jsonl` và đoạn nguồn theo trang/offset. Các file này vẫn giữ local; quyền xem PDF không tự biến thành quyền sao chép hoặc công bố toàn bộ file dẫn xuất.
4. Đối chiếu score người dùng xác nhận trong review local với các bảng tổng hợp. Metadata là `USER_ACCEPTED_TECHNICAL_VERIFICATION`, không phải independent manual scoring. Extraction được chấp nhận với29warning pages giữ nguyên; không phải toàn bộ trang đã human-verified.
5. Từ `starter/`, tác giả chạy `.venv/Scripts/python -m src.submission` để kiểm tra artifact đã lưu, không tạo embeddings hoặc chạy retrieval mới. Từ repo root chạy `starter/.venv/Scripts/python -m unittest discover -s tests -v` trên nguồn/cache thật.

Public checkout đơn lẻ thiếu nguồn, gold và trace nên không tái lập full benchmark. Đây là giới hạn công bố theo SUBMISSION.md; không dùng data giả để lấp chỗ thiếu. Nếu giảng viên cần nhận bản sao thay vì xem riêng, phải xác định quyền/phương thức chia sẻ hợp lệ trước; tác vụ hiện tại không tự thực hiện việc chuyển tài liệu.

D10/trang106 và78candidate chunks chỉ phân tích định tính, chưa được thêm vào gold và không làm thay đổi test hồi tố. C/T05 có2hit hợp lệ, rank 3 N/A; không có bản ghi thứ ba bị giấu hoặc tạo thay thế.
