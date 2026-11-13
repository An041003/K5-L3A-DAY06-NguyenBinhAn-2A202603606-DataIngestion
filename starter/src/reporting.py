"""Produce a source-free submission from measured artifacts, with honest pending gates."""
import csv
import json
import statistics
from pathlib import Path
from .io_utils import read_jsonl, write_json


def generate(root: Path):
    private = root/'.agents'
    results = root/'results'
    def read(path, default=None):
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    manifest = read(root/'data/manifest.json')
    chunks = read(results/'chunk_statistics.json')
    ingest = read(results/'ingest_statistics.json')
    frozen = read(private/'benchmark/lock.json')
    trace_path = private/'results/traces.jsonl'
    traces = read_jsonl(trace_path) if trace_path.exists() else []
    complete = len(traces) == 60
    returned_records = sum(len(t['hits']) for t in traces)
    test_metadata_records = sum(len(t['hits']) for t in traces if t['split']=='test')
    metrics = []
    if complete:
        with (results/'metrics.csv').open(encoding='utf-8') as f:
            metrics = list(csv.DictReader(f))
    usage_path = private/'cache/api_usage.jsonl'
    usage = read_jsonl(usage_path) if usage_path.exists() else []
    token_values = [(u.get('usage') or {}).get('prompt_tokens') for u in usage]
    cost_values = [(u.get('usage') or {}).get('cost') for u in usage]
    measured_tokens = sum(token_values) if token_values and all(v is not None for v in token_values) else None
    measured_cost = sum(cost_values) if cost_values and all(v is not None for v in cost_values) else None
    cost = {'successful_batches':len(usage),'inputs':sum(u['inputs'] for u in usage),
        'measured_prompt_tokens':measured_tokens,'provider_reported_cost_usd':measured_cost,
        'estimated_cost_usd':measured_tokens*0.20/1e6 if measured_tokens is not None else None,
        'estimate_rate_usd_per_million':0.20,'pricing_checked_date':'2026-11-13',
        'scope':'successful document/query pipeline requests; separate public smoke excluded (2 tokens); failed unknown charges not asserted'}
    write_json(results/'api_usage_summary.json',cost)
    timing = []
    for s in ('A','B','C'):
        times = [t['search_seconds'] for t in traces if t['strategy']==s]
        timing.append({'strategy':s,'queries':len(times),'search_sum_seconds':sum(times) if times else None,
            'search_median_seconds':statistics.median(times) if times else None,
            'note':'local client wall time includes database connection; shared query embedding timed separately in private trace'})
    write_json(results/'search_timing.json',timing)
    questions = {q['id']:q for q in read_jsonl(private/'benchmark/questions.jsonl')}
    failures = []
    for t in traces:
        if not t['evaluation']['evidence_hit_at_3']:
            gold_page_seen = any(h['page']==t['gold_page'] and h['document_id']==t['gold_source_id'] for h in t['hits'])
            failures.append({'question_id':t['id'],'split':t['split'],'strategy':t['strategy'],
                'source_id':t['gold_source_id'],'original_gold_page':t['gold_page'],
                'top3_original_pages':[h['page'] for h in t['hits']],
                'gold_offsets':[questions[t['id']]['evidence_start'],questions[t['id']]['evidence_end']],
                'returned_gold_page_offsets':[[h['metadata']['start'],h['metadata']['end']] for h in t['hits'] if h['page']==t['gold_page']],
                'technical_failure':'COMPLETE_QUOTE_NOT_IN_SINGLE_RETURNED_CHUNK' if gold_page_seen else 'GOLD_PAGE_NOT_IN_TOP3',
                'human_evidence_judgment':'PENDING_HUMAN'})
    write_json(results/'failure_summary.json',failures)
    metric_table = '\n'.join(f"| {m['strategy']} | {m['split']} | {m['hit_at_1_n']}/{m['n']} ({float(m['hit_at_1']):.1%}) | {m['evidence_hit_at_3_n']}/{m['n']} ({float(m['evidence_hit_at_3']):.1%}) |" for m in metrics)
    if not metric_table:
        metric_table = '\n'.join(f'| {s} | {split} | NOT_RUN | NOT_RUN |' for s in ('A','B','C') for split in ('dev','test'))
    selection = read(private/'results/selection_before_test.json',{})
    hypothesis = {'A':'Short overlapping windows provide localized retrieval but may split conditions.',
        'B':'Larger source-bounded paragraph/line groups may preserve evidence at increased per-chunk length.',
        'C':'Source-proven question scope may remove off-scope hits; wrong input scope can exclude valid evidence.'}
    experiment_rows = []
    for s in ('A','B','C'):
        row = {'strategy':s,'chunking':'fixed' if s=='A' else 'paragraph/line, chapter bounded',
            'chunk_size':500 if s=='A' else 1100,'overlap':50 if s=='A' else 0,
            'metadata':'document_id,source,original_page,pdf_page,section,source_offsets,heading_provenance',
            'filter':'question-supplied section in SQL' if s=='C' else 'none',
            'vectorizer':'OpenRouter google/gemini-embedding-2 / 768 / pgvector cosine exact',
            'hypothesis':hypothesis[s]}
        for split in ('dev','test'):
            m = next((m for m in metrics if m['strategy']==s and m['split']==split),None)
            row[f'{split}_hit1'] = f"{m['hit_at_1_n']}/{m['n']}" if m else 'NOT_RUN'
            row[f'{split}_hit3'] = f"{m['evidence_hit_at_3_n']}/{m['n']}" if m else 'NOT_RUN'
        row['notes'] = 'PROVISIONAL exact-quote proxy; human gold/manual review PENDING; C shares B vectors; no test retuning'
        experiment_rows.append(row)
    with (root/'artifacts/experiment_log.csv').open('w',encoding='utf-8',newline='') as f:
        w = csv.DictWriter(f,fieldnames=list(experiment_rows[0]))
        w.writeheader()
        w.writerows(experiment_rows)
    cases=[]
    seen=set()
    # Show both a fragmented-evidence case and a missing-gold-page case where available.
    chosen = []
    for kind in ('COMPLETE_QUOTE_NOT_IN_SINGLE_RETURNED_CHUNK','GOLD_PAGE_NOT_IN_TOP3'):
        candidate = next((f for f in failures if f['technical_failure']==kind),None)
        if candidate:
            chosen.append(candidate)
    for failure in chosen:
        if failure['question_id'] in seen:
            continue
        seen.add(failure['question_id'])
        cases.append(f"- `{failure['question_id']}`, strategy {failure['strategy']}, nguồn `{failure['source_id']}`, trang gốc {failure['original_gold_page']}: top-3 tại {failure['top3_original_pages']}; `{failure['technical_failure']}`. Đây là lỗi theo proxy kỹ thuật; phải đọc trace riêng trước khi chốt thiếu evidence về nghĩa.")
        if failure['returned_gold_page_offsets']:
            cases.append(f"  Gold chiếm offsets {failure['gold_offsets']}; chunk trả về ở trang gold chiếm {failure['returned_gold_page_offsets']}. Ranh giới cửa sổ làm mất một phần quote nên không được tính hit theo định nghĩa một chunk đủ evidence; không cộng nhiều chunk để thay metric chính.")
        else:
            cases.append('  Không trả về trang gold đã khai báo trong top-3; có thể do nội dung tương tự ở nhiều trang. Phải đối chiếu evidence tương đương trước khi kết luận là lỗi về nghĩa; không thêm alternate gold sau test để nâng số đo hiện tại.')
    if not cases:
        cases=['- Chưa có failure retrieval đo được để phân tích: NOT_RUN. Không tạo ví dụ giả.']
    warning_pages = sum(bool(p['warnings']) for p in manifest['pages'])
    audit_count = 30+test_metadata_records+15 if complete else 'PENDING_RETRIEVAL'
    if complete:
        write_json(results/'trace_integrity_summary.json',{'trace_records':len(traces),'returned_chunk_records':returned_records,
            'expected_max_chunk_records':180,'test_metadata_records':test_metadata_records,
            'manual_ratable_rows':audit_count,'audit_shortfall_rows':180-returned_records,
            'shortfalls':[{'question_id':t['id'],'strategy':t['strategy'],'returned':len(t['hits']),
                'reason':'only two B chunks in requested section; C returns available eligible rows'} for t in traces if len(t['hits'])<3],
            'human_gold_status':'PENDING_HUMAN'})
    report = f'''# Báo cáo cá nhân — Lab Day 06

Học viên: **NguyenBinhAn — 2A202603606 — L3A** (theo tên repo được người dùng cung cấp; dấu tiếng Việt của họ tên: PENDING_USER).

Trạng thái: **PARTIAL — PENDING_HUMAN**. {'A/B/C đã chạy đủ; số đo dưới đây là kết quả kỹ thuật tạm thời trên gold do AI soạn, chưa được người dùng duyệt.' if complete else 'Retrieval benchmark NOT_RUN; chưa được phép gửi question text tới provider. Đã hoàn thành các phần offline và embedding document được phép.'} Chưa đủ điều kiện tuyên bố hoàn tất rubric hoặc nộp chính thức. Không push.

## Dữ liệu và pipeline

Corpus là trích đoạn tài liệu thiết kế KPI nội bộ, một nguồn `kpi-v2`. Có **42 trang vật lý, 42 trang nội dung**, gồm trang gốc **7–17 và 81–111**; **{manifest['characters']:,} ký tự** sau chuẩn hóa. Kiểm tra riêng từng trang: không có bìa, mục lục, trang trống hoặc trang chỉ có tài liệu tham khảo; trang 111 là ma trận truy vết nguồn–thiết kế có nội dung nghiệp vụ. Không áp ngưỡng 1.500 ký tự của text không phân trang lên PDF.

SHA-256 PDF: `{manifest['sha256']}`. Manifest chứa ánh xạ và số ký tự từng trang tại `data/manifest.json`. Quyền: người dùng xác nhận xử lý local, gửi chunk và 20 question text tới OpenRouter/Google ngày 13/11/2026; hai xác nhận được ghi riêng trong hồ sơ local. **Chưa có quyền tái phân phối** PDF, text, gold hoặc trace đầy đủ. Việc người chấm tiếp cận nguồn/benchmark còn PENDING_AUTHORIZED_ACCESS; số liệu tổng hợp không thay cho full trace.

RAW PDF → trích xuất từng trang → bỏ running header và nhãn trang lặp → Unicode NFC/whitespace, giữ line breaks → gán chapter và offsets → chunk A/B → embeddings API → PostgreSQL/pgvector → top-3 → proxy/nhãn review. `original_page` là page/gold_page chính thức; `pdf_page` là vị trí mở PDF rút gọn. Có khoảng trống trang 18–80 nên không lan metadata qua khoảng trống.

Parser chính pypdf 6.21.4; PyMuPDF 1.27.2.3 được dùng cho trang gốc **12, 13, 93** vì pypdf trả control characters trong công thức/cấu hình. Không tự viết lại công thức. Có **28 trang cảnh báo reading order bảng**, tổng **{warning_pages} trang có ít nhất một cảnh báo**. Nội dung cảnh báo và body giữ local ở `.agents/processed/pages.jsonl`; manifest chỉ công bố loại cảnh báo/trang. Kiểm tra con người về thứ tự bảng: PENDING_HUMAN.

ID chunk là SHA-256 của document/page/cấu hình/offset/text/metadata nguồn. Upsert trong transaction với khóa bảng, xóa ID cũ không còn trong snapshot của từng tài liệu rồi ghi mới; lỗi count, vector chiều sai, nonfinite, filter ngoài allowlist chặn xử lý. Không có local embedding hoặc vector giả. Cache nằm local, khóa theo hash text + model + dimensions + encoding contract; C dùng chính dòng B. Ghi usage từng request thành công; timeout không tự gửi lại vì chưa biết đã bị tính phí hay chưa; 429/503 retry tối đa 3 lần, backoff hữu hạn.

## Model, backend và chi phí

- OpenRouter `POST /api/v1/embeddings`; `google/gemini-embedding-2`, **768 dimensions**, document và query cùng raw text, không task prefix khác nhau. Không dùng chat completions. Vector trả về được kiểm tra count/index/finite/chiều/nonzero. Giới hạn mỗi input là 8.192 byte UTF-8 bảo thủ; không giả định đã chạy tokenizer của model.
- PostgreSQL **{ingest['backend']['postgresql']}**, pgvector **{ingest['backend']['pgvector']}**, cosine `<=>`, **exact search**, không ANN. Docker image `pgvector/pgvector:0.8.7-pg16`, named volume `day6_nguyenbinhan_pg_data`; cổng local 55433. Bộ A/B lưu 306 dòng trong bảng `day06_chunks`; C ánh xạ B, không có index duplicate.
- Smoke test từ script có sẵn: thành công, **768 dimensions, 2 prompt tokens**, chỉ câu công khai. Phép thử này không phải benchmark.
- Pipeline usage đo được: **{cost['measured_prompt_tokens']} prompt tokens**, **{cost['inputs']} input**, **{cost['successful_batches']} request batch thành công**. Provider trả `usage.cost` tổng **{cost['provider_reported_cost_usd']} USD**. Giá tham chiếu kiểm tra 13/11/2026: 0,20 USD/triệu text tokens; ước tính từ usage là **{cost['estimated_cost_usd']} USD**. Khoản này loại smoke test riêng 2 tokens; không thay cho đối soát hóa đơn tài khoản. Không ghi 0 cho chi phí chưa đo.
- API và thông số đối chiếu với [OpenRouter Embeddings](https://openrouter.ai/docs/api/api-reference/embeddings/submit-an-embedding-request), [model/pricing](https://openrouter.ai/google/gemini-embedding-2), [pgvector](https://github.com/pgvector/pgvector). Phiên bản package và thời điểm chạy ở `results/run_environment.json` nếu retrieval đã chạy.

## Metadata và ba cấu hình

Mỗi chunk có document_id/source/page, pdf_page/original_page, start/end, `section` kiểu string, heading provenance. `section` là chapter heading **thực trong nguồn**, truyền xuống các trang liên tiếp và cắt chunk tại chapter boundary; không suy đoán theo tên file hoặc gold. Corpus có **17 giá trị chapter**; không dùng year/version gần như hằng số để tạo lợi ích filter giả. Một số chapter chỉ xuất hiện một phần trong trích đoạn; metadata không cam kết chứa trọn chương.

| Cấu hình | Tham số | Số chunk | Min / median / max ký tự | Tổng ký tự |
|---|---|---:|---|---:|
| A | fixed 500 ký tự, overlap 50, giới hạn page/chapter | {chunks['A']['chunks']} | {chunks['A']['min']} / {chunks['A']['median']} / {chunks['A']['max']} | {chunks['A']['characters']} |
| B | paragraph/line packing tối đa 1.100 ký tự, word fallback, không overlap | {chunks['B']['chunks']} | {chunks['B']['min']} / {chunks['B']['median']} / {chunks['B']['max']} | {chunks['B']['characters']} |
| C | cùng chunk/vector với B; chỉ filter section theo input câu hỏi tại SQL | {chunks['C']['chunks']} (dùng B) | giống B | giống B |

A–B thay chính sách chunking (kích thước, overlap và boundary packing được nêu rõ); B–C chỉ đổi filter ở retrieval. Mọi cấu hình dùng cùng corpus, câu hỏi, model, dimensions, store, cosine và top-3. Bỏ whitespace ở mép chunk nên tổng ký tự B thấp hơn text trang; test bảo toàn mọi ký tự không phải whitespace đã kiểm tra.

## Benchmark và cách đánh giá

**20 câu, 15 dev/5 test**, gồm hỏi trực tiếp, paraphrase, điều kiện/ngoại lệ; **5 câu filter, 2 câu filter test**. AI soạn từ các trang thật trước retrieval, kiểm tra exact span của evidence và filter khớp chapter nguồn; `human_verified=false`. Draft gold ở `.agents/benchmark/questions.jsonl`; bản duyệt ở `.agents/review/gold_review.csv`, hiện **PENDING_HUMAN**. Chưa chứng minh gold có đủ mọi nguồn tương đương; reviewer phải bổ sung các gold thay thế hợp lệ.

Split theo chủ đề: dev phần quy tắc/quyền/yêu cầu/kiến trúc; test API conventions và vận hành/nghiệm thu. Một tài liệu dùng chung từ vựng, điều kiện có thể lặp; đây không phải holdout độc lập theo tài liệu. Không retune theo kết quả test. Question filter nói rõ chapter scope từ trước retrieval; A/B vẫn thấy cùng question text, C mới áp lọc SQL. Vì câu hỏi đã chứa ngữ cảnh chapter nên mức lợi ích filter có thể nhỏ.

Hash bộ benchmark trước retrieval: `{frozen['benchmark_sha256']}`; thời điểm lock `{frozen['at']}`. Tiêu chí chọn đã khóa: **dev Evidence Hit@3 → dev Hit@1 → ít chunk lưu hơn → thứ tự strategy**. Lựa chọn được ghi trước test retrieval tại `.agents/results/selection_before_test.json`; lựa chọn tạm thời: **{selection.get('selected','NOT_RUN')}**. Chưa dùng coherence/grounding người chấm để ra kết luận cuối.

Proxy kỹ thuật: cùng source_id/trang gốc và **toàn bộ evidence_quote** sau normalize whitespace nằm trong một chunk. Chấp nhận bất kỳ gold alternative đã khai báo. Hit@1 = số top-1 hit/N; Evidence Hit@3 = số câu có ≥1 hit trong top-3/N. Không coi việc khớp một đoạn ngắn, chỉ đúng trang, hợp evidence từ nhiều chunk, hoặc nhãn AI là nhãn người. Khi gold chưa duyệt, các chỉ số sau **không phải độ chính xác cuối cùng**.

## Kết quả đo thật

| Strategy | Split | Hit@1, n/N (%) | Evidence Hit@3, n/N (%) |
|---|---|---|---|
{metric_table}

Ingest đầu tiên: A **{ingest['A']['ingest_seconds']:.3f}s**, B **{ingest['B']['ingest_seconds']:.3f}s** (gồm API/cache lookup và write đầu, không gồm setup/parser). B có 8 text trùng A đã được tái sử dụng; C không có lần gọi document embedding riêng. Write lại cùng vectors: A **{ingest['A']['second_write_seconds']:.3f}s**, B **{ingest['B']['second_write_seconds']:.3f}s**, count/IDs không đổi. Đây là một lần đo wall time, không phải benchmark hiệu năng nhiều lượt. Số đo search ở `results/search_timing.json`, gồm mở connection local; query embedding chia sẻ cùng một vector cho A/B/C.

Đã kiểm tra xóa stale chunk ID bằng một technical fixture từ chính chunk thật, sau đó khôi phục đầy đủ corpus trước retrieval. Chi tiết source-free ở `results/storage_verification.json`. Kiểm tra restart/persistence ở `results/persistence_verification.json` nếu có. Các phép thử kỹ thuật không được tính vào benchmark corpus hoặc usage token giả.

| Strategy | Coherence /2 (10 vị trí) | Metadata đủ/đúng (số bản ghi thực) | Filter compliance | Grounding /2 (5 câu) |
|---|---|---|---|---|
| A | PENDING_HUMAN | PENDING_HUMAN (15) | N/A (không áp lọc); quan sát scope 2/2 | PENDING_HUMAN |
| B | PENDING_HUMAN | PENDING_HUMAN (15) | N/A (không áp lọc); quan sát scope 1/2 | PENDING_HUMAN |
| C | PENDING_HUMAN | PENDING_HUMAN (14) | 2/2 scope trên hit thực; 1/2 đủ ba hit | PENDING_HUMAN |

Coherence: cùng 10 vị trí nguồn trên 10 trang đầu, offset min(200, len−1), chọn chunk đầu tiên bao phủ vị trí; chấm 0/1/2 và lý do. Metadata: mục tiêu tối đa 45 bản ghi test, thực nhận **{test_metadata_records}**; grounding: 5 test×3 =15 mẫu. Có **{audit_count} mẫu có thể chấm**, cộng 1 dòng ghi thiếu kết quả (NOT_APPLICABLE) trong `.agents/review/manual_audit_template.csv`. Riêng C/T05 chỉ có 2 chunk B thuộc section được yêu cầu, nên không có kết quả thứ ba; không nhân đôi hoặc tạo giả để đủ top-3. Filter compliance trên các kết quả thực nhận là 2/2 query C; full-top-3 scope compliance là 1/2. Đây là giới hạn độ phủ của corpus/chunking, không có hit ngoài scope. **Không có điểm trung bình người chấm do AI điền**. Cần tác giả xác nhận và ghi nguy cơ thiên lệch.

Trace đầy đủ (text, score, metadata, filters, gold, proxy từng câu) giữ local `.agents/results/traces.jsonl` (**{len(traces)} dòng, {returned_records} chunk records**; tối đa 180). Public repo chỉ có metrics tổng hợp, thống kê, hash và failure ID/trang; người chấm cần quyền riêng để xem nguồn/evidence. Không publish nội dung KPI để làm đủ checklist.

## Năm khía cạnh và phân tích

1. **Retrieval accuracy:** bảng trên tách dev/test, hiển thị tử/mẫu và %. Mẫu test chỉ 5 câu; mỗi câu đổi kết quả làm thay đổi 20 điểm phần trăm. Proxy chưa thay gold đã duyệt.
2. **Chunk coherence:** B giữ boundary dòng/đoạn và nhiều ngữ cảnh hơn A nhưng có thể vẫn cắt cấu trúc bảng nhiều trang. Điểm thực tế PENDING_HUMAN, chưa kết luận B mạch lạc hơn chỉ từ độ dài.
3. **Metadata usefulness:** original_page/pdf_page giúp mở đúng trang nguồn; section giúp giới hạn phạm vi trong SQL. Hạn chế: chapter khá rộng, trích đoạn không liên tục và headings có thể bắt đầu giữa trang; scope sai sẽ loại evidence đúng. Mechanical compliance không chứng minh metadata đúng hay hữu ích về nghĩa.
4. **Grounding quality:** đang đánh giá evidence retrieval, không gọi LLM sinh đáp án. Mean/phân bố 0/1/2 PENDING_HUMAN; exact quote chỉ là proxy hỗ trợ reviewer.
5. **Data strategy impact:** A có 202 chunk, B có 104, giảm **{(1-104/202):.1%}** số dòng/vector; A thêm overlap nên tăng tổng ký tự được gửi. B lớn hơn dễ chứa cả điều kiện nhưng mỗi vector bao phủ nhiều ý. Dev Hit@3 B/C cùng 12/15, hơn A 11/15; C được chọn tạm thời vì dev Hit@1 8/15 so với B 7/15. Test B/C cùng Hit@3 3/5, A 2/5; không có bằng chứng từ mẫu test này cho thấy C tăng Hit@3 so với B. C loại hit ngoài scope ở T05 nhưng chỉ còn hai kết quả. Đọc kết quả cùng manual audit trước quyết định cuối, không thay tham số sau test.

Các case lỗi kỹ thuật đã chạy (nội dung nguồn giữ riêng):

{chr(10).join(cases)}

Phân tích sâu điều kiện còn thiếu và xác nhận bằng chứng tương đương trong các case: PENDING_HUMAN. Không chỉnh tham số hoặc test sau khi thấy các lỗi trên. Muốn sửa chunk/query phải lập thí nghiệm mới trên dev, giữ lịch sử và có holdout mới phù hợp.

## Tái lập, giới hạn và việc còn chờ

Các lệnh và điều kiện dữ liệu ở README; tests chạy trên corpus thật/cache thật, không download embedding local. Source và benchmark không thể tái lập từ public checkout đơn lẻ khi chưa được cấp quyền; báo cáo công khai ghi rõ giới hạn này. Không giả định artifact tổng hợp đủ cho chấm full rubric.

PENDING: duyệt 20 gold và alternate evidence; chấm {audit_count} mẫu audit và kiểm tra 1 shortfall; kiểm tra thứ tự bảng/đoạn PDF; xác nhận họ tên có dấu; cấp quyền cho người chấm truy cập private source/benchmark/traces; chốt báo cáo sau manual review; người dùng cho phép push/nộp.

Công cụ hỗ trợ: Codex soạn code/câu hỏi/phân tích; OpenRouter chỉ tạo embedding. Người dùng phải hiểu code và tự xác minh evidence/nhãn. Không tạo dữ liệu, vector, kết quả, nguồn hoặc nhãn thủ công giả.
'''
    target=root/'report/individual/2A202603606_NguyenBinhAn.md'
    target.write_text(report,encoding='utf-8')
    print(f'Wrote source-free report: {target.name}; status PARTIAL/PENDING_HUMAN')
