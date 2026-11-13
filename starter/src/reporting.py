"""Final source-free report. Original experiment files are read-only inputs."""
import csv
import json
from pathlib import Path
from .human_review import aggregate_human_review
from .io_utils import read_jsonl, write_json


def _json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def generate(root: Path):
    private, results = root/'.agents', root/'results'
    human = aggregate_human_review(root)
    if not human or human['status']!='FINAL_REVIEW_ACCEPTED_WITH_LIMITATIONS':
        raise RuntimeError('BLOCKED: explicit final review decisions required')
    manifest = _json(root/'data/manifest.json')
    chunks = _json(results/'chunk_statistics.json')
    ingest = _json(results/'ingest_statistics.json')
    warm = _json(results/'ingest_latest.json')
    usage = _json(results/'api_usage_summary.json')
    timing = {r['strategy']:r for r in _json(results/'search_timing.json')}
    frozen = _json(private/'benchmark/lock.json')
    selection = _json(private/'results/selection_before_test.json')
    traces = read_jsonl(private/'results/traces.jsonl')
    with (results/'metrics.csv').open(encoding='utf-8',newline='') as f:
        metrics = list(csv.DictReader(f))
    if len(traces)!=60 or sum(len(t['hits']) for t in traces)!=179 or selection['selected']!='C':
        raise ValueError('Frozen experiment incomplete or selection changed')
    write_json(results/'human_review_summary.json',human)
    fields=['strategy','coherence_n','coherence_sum','coherence_mean_out_of_2','grounding_n','grounding_sum','grounding_mean_out_of_2','grounding_0','grounding_1','grounding_2','label_origin','metadata_accepted_n','metadata_total','metadata_status','metadata_independently_human_scored']
    with (results/'manual_evaluation_summary.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for s in ('A','B','C'):
            c,g,m=human['coherence'][s],human['grounding'][s],human['metadata']['by_strategy'][s]
            writer.writerow({'strategy':s,'coherence_n':c['n'],'coherence_sum':c['sum'],'coherence_mean_out_of_2':f"{c['mean']:.2f}",'grounding_n':g['n'],'grounding_sum':g['sum'],'grounding_mean_out_of_2':f"{g['mean']:.2f}",**{f'grounding_{i}':g['distribution'][str(i)] for i in (0,1,2)},'label_origin':'USER_CONFIRMED','metadata_accepted_n':m['accepted'],'metadata_total':m['total'],'metadata_status':human['metadata']['status'],'metadata_independently_human_scored':False})
    metric_table='\n'.join(f"| {m['strategy']} | {m['split']} | {m['hit_at_1_n']}/{m['n']} ({float(m['hit_at_1']):.1%}) | {m['evidence_hit_at_3_n']}/{m['n']} ({float(m['evidence_hit_at_3']):.1%}) | {chunks[m['strategy']]['chunks']} |" for m in metrics)
    quality_table='\n'.join(f"| {s} | {human['coherence'][s]['mean']:.2f} (10) | {human['metadata']['by_strategy'][s]['accepted']}/{human['metadata']['by_strategy'][s]['total']} | {'N/A; quan sát scope 2/2' if s=='A' else 'N/A; quan sát scope 1/2' if s=='B' else '2/2 hit trong scope; 1/2 đủ 3 hit'} | 0 / 1 / 4; {human['grounding'][s]['mean']:.2f} (5) |" for s in ('A','B','C'))
    time_table='\n'.join(f"| {s} | {ingest[s]['ingest_seconds']:.3f} | {ingest[s]['second_write_seconds']:.3f} | {warm[s]['ingest_seconds']:.3f} | {timing[s]['search_median_seconds']*1000:.2f} |" for s in ('A','B'))
    time_table+=f"\n| C | dùng B | dùng B | dùng B | {timing['C']['search_median_seconds']*1000:.2f} |"
    resources=_json(results/'resource_snapshot.json') if (results/'resource_snapshot.json').exists() else {}
    resource_note=(f"Đo read-only cuối: {resources['database_rows']} dòng; bảng và index PostgreSQL chiếm {resources['pg_total_relation_bytes']:,} byte, gồm text/metadata/vector/index." if resources.get('status')=='MEASURED' else 'Dung lượng vật lý DB chưa đo ở final review; không báo số giả.')
    metric_table='\n'.join(f"| {m['strategy']} | {m['split']} | {m['hit_at_1_n']}/{m['n']} | {m['evidence_hit_at_3_n']}/{m['n']} | {chunks[m['strategy']]['chunks']} | {format(ingest[m['strategy']]['ingest_seconds'],'.3f')+' s ingest' if m['strategy']!='C' else 'Dùng B'} | Dùng chung |" for m in metrics)
    report=f'''# Báo cáo cá nhân — Day 6

## Dữ liệu và pipeline

- Chủ đề, nguồn/quyền, số trang và quy tắc tính trang: Tài liệu thiết kế KPI nội bộ, nguồn `kpi-v2`, 42 trang nội dung (trang gốc 7–17 và 81–111); loại bìa, mục lục, trang trống và trang chỉ có tài liệu tham khảo. Được phép xử lý và cho người chấm xem riêng; không công bố corpus, gold hoặc full trace. Nguồn và cách truy cập: `data/manifest.json`, `data/ACCESS.md`.
- Chuẩn hóa, lỗi và giới hạn: PDF → trích xuất từng trang → Unicode NFC, chuẩn hóa whitespace → chunk → embedding → pgvector. Dùng pypdf 6.21.4, fallback PyMuPDF 1.27.2.3 tại trang 12, 13, 93. Giữ 29 trang có cảnh báo, gồm 28 trang reading order bảng. Extraction được chấp nhận với giới hạn; chưa kiểm tra toàn diện từng trang, không coi là hoàn toàn không lỗi.
- Embedding model/provider/version/số chiều, vector store/version, metric, lệnh chạy và chi phí: OpenRouter `google/gemini-embedding-2`, 768 dimensions; PostgreSQL 16.16 + pgvector 0.8.7, cosine exact. Chạy từ `starter/`: `python -m src.run ingest --allow-external` và `python -m src.run benchmark --allow-external --allow-unverified` (lệnh thí nghiệm đã thực hiện). Tổng API: {usage['measured_prompt_tokens']:,} tokens, **{usage['provider_reported_cost_usd']:.7f} USD**, dùng chung A/B/C; không phân bổ riêng theo split. Nạp lại không tăng số dòng; dữ liệu tồn tại sau restart DB.
- Metadata bắt buộc, trường lọc bổ sung, nguồn giá trị và lý do chọn: `document_id`, `source`, `page=original_page`, `pdf_page`, offsets và `section`. Section lấy từ chapter heading thật để lọc phạm vi; page map dùng truy đúng trang nguồn. Chunk ID theo hash, giữ lineage tới source spans và kiểm tra dimension/nguồn/trang trước khi lưu.

## Cấu hình và benchmark

- A / B / C (tham số cụ thể, khác biệt duy nhất B–C): A fixed 500 ký tự, overlap 50, 202 chunk; B paragraph/line tối đa 1.100 ký tự, không overlap, 104 chunk. C dùng chính chunk/vector B, chỉ thêm section filter khi question cung cấp scope. Cùng corpus, model, dimensions, backend và cosine.
- ≥20 câu: phân chia ≥15 dev / ≥5 test, câu metadata filter và cách kiểm chứng evidence: 20 câu (15 dev/5 test), 5 câu filter, gồm 2 test. Đã đối chiếu evidence với trang nguồn và người dùng xác nhận 20/20 gold chính. Giữ nguyên benchmark; hit yêu cầu đúng source/page và chứa toàn bộ quote trong một chunk.
- Tiêu chí chọn chiến lược đã chốt trước khi xem test: Dev Evidence Hit@3 → Hit@1 → ít chunk → thứ tự strategy; đã chọn C trước test. Không chỉnh cấu hình theo test.

## Kết quả

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---|---|---|---|---|---|
{metric_table}

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
{quality_table}

Đường dẫn trace, nhãn thủ công và cách chọn mẫu: `.agents/results/traces.jsonl`, `.agents/review/manual_audit_template.csv`; số tổng hợp tại `results/metrics.csv`, `results/manual_evaluation_summary.csv`. Coherence: cùng 10 vị trí nguồn đã khóa trước search, đủ 30 nhãn xác nhận. Grounding: đủ 5 test/strategy, T01=1, T02–T05=2; giữ nguyên điểm và nhận xét đã có. Metadata 44/44 là **USER_ACCEPTED_TECHNICAL_VERIFICATION**, không phải người dùng tự chấm độc lập từng chunk. C/T05 chỉ có 2 hit hợp lệ: rank 3 N/A; scope tuân thủ 2/2 query nhưng chỉ 1/2 query đủ 3 hit. Thời gian trong bảng là ingest dùng cho cả hai split, không cộng hai lần.

## Phân tích và kết luận

- So sánh A–B và B–C; 2 ví dụ sai có ID câu và nguồn: B giảm 202→104 chunk, coherence tăng 1.00→1.50; test Hit@3 tăng 2/5→3/5 so với A. C tăng dev Hit@1 từ 7/15→8/15 so với B, nhưng test B/C giống nhau. D10/A, `kpi-v2` trang 17: chunk trả về thiếu đầu quote; D10/trang106 vẫn PENDING, không thêm vào gold. D01/A, `kpi-v2` trang 7: top-3 tại trang 93/106/105, không có trang gold nên không tính hit.
- Chiến lược chọn, đánh đổi, điều kiện áp dụng: Giữ C theo tiêu chí dev; dùng khi scope đáng tin, không có scope thì tương đương B. Filter có thể giảm số kết quả; không khẳng định C tốt hơn B trên test.
- Hạn chế của dữ liệu, nhãn, test nhỏ, đo thời gian/chi phí: Một tài liệu, chỉ 5 test, có nội dung lặp; metadata là kiểm chứng kỹ thuật được chấp nhận, khác manual audit độc lập. Giữ 29 cảnh báo extraction; 78 candidate chunks chỉ định tính, không hồi tố test. Thời gian đo một lượt, không kiểm định thống kê; chi phí là provider-reported usage. Public checkout không chứa dữ liệu hạn chế nên cần quyền xem riêng để kiểm chứng.
- Nếu làm lại hoặc mở rộng, cải tiến gì? Thử chunking nhận biết bảng/đoạn, giữ ngữ cảnh bảng nối trang; bổ sung gold thay thế sau xác minh và đánh giá trên holdout mới lớn hơn. Không thay đổi phép đo đã khóa hiện tại.
'''
    target=root/'report/individual/2A202603606_NguyenBinhAn.md'
    target.write_text(report,encoding='utf-8')
    print(f'Final report generated: {target.name}; no experiment mutation or API calls')