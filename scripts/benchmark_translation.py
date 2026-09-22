# -*- coding: utf-8 -*-
"""
Script Benchmark Hiệu Năng Dịch Thuật Đa Luồng NovaCut
Model: qwen/qwen3.7-flash qua OpenRouter (provider: {sort: "throughput"})
Đo đạc Wall-clock time thực tế cho các mức Concurrency: 1, 4, 6, 8
"""

import os
import sys
import time
import json
import concurrent.futures
import openai

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from translation_config import DEFAULT_TRANSLATION_MODEL, DEFAULT_TRANSLATION_CONFIG
from routes.state import API_KEYS_FILE

def load_credentials():
    api_key = os.environ.get('OPENAI_API_KEY', '')
    base_url = 'https://openrouter.ai/api/v1'
    model = DEFAULT_TRANSLATION_MODEL

    if os.path.exists(API_KEYS_FILE):
        with open(API_KEYS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('openaiKey='):
                    k = line.strip().split('=', 1)[1]
                    if k and not k.startswith('•'):
                        api_key = k
                elif line.startswith('openaiBaseUrl='):
                    u = line.strip().split('=', 1)[1]
                    if u: base_url = u
                elif line.startswith('openaiModel='):
                    m = line.strip().split('=', 1)[1]
                    if m: model = m
    return api_key, base_url, model

SAMPLE_CHINESE_LINES = [
    "师尊，你怎么来了？",
    "弟子拜见师尊。",
    "此事与你无关，速速退下。",
    "今日青云宗有大敌来犯，不可大意。",
    "难道是万毒门的妖人？",
    "正是，他们布下了九幽玄天大阵。",
    "弟子愿随师尊一同迎敌！",
    "你不过刚入筑基期，如何抵挡金丹老怪？",
    "纵然粉身碎骨，弟子也绝不退缩！",
    "好，不愧是我青云宗门下。"
]

def generate_chunk(chunk_size=70, start_id=1):
    chunk = []
    for i in range(chunk_size):
        idx = start_id + i
        txt = SAMPLE_CHINESE_LINES[i % len(SAMPLE_CHINESE_LINES)]
        chunk.append({"id": str(idx), "text": txt})
    return chunk

def translate_chunk(client, model, chunk, worker_id):
    system_prompt = (
        "Bạn là công cụ dịch phụ đề chuyên nghiệp từ tiếng Trung sang tiếng Việt.\n\n"
        "Nhiệm vụ:\n"
        "Dịch thoại phim Trung Quốc sang tiếng Việt tự nhiên, chính xác và phù hợp ngữ cảnh.\n\n"
        "Quy tắc:\n"
        "- Không dịch máy từng chữ.\n"
        "- Giữ đúng ý nghĩa câu gốc.\n"
        "- Văn phong tự nhiên như phụ đề phim Việt Nam.\n"
        "- Không tự ý giải thích, không thêm chú thích.\n\n"
        "Input có dạng:\nID|Chinese text\n\nOutput bắt buộc có dạng:\nID|Vietnamese translation\n\n"
        "Mỗi subtitle input phải có đúng một subtitle output.\n"
        "Chỉ output các dòng cần dịch.\nKhông output context được cung cấp để tham khảo."
    )
    
    trans_lines = [f"{s['id']}|{s['text']}" for s in chunk]
    user_msg = "[TRANSLATE]\n" + "\n".join(trans_lines)
    
    t0 = time.perf_counter()
    resp = None
    last_err = None
    
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg}
                ],
                temperature=0.0,
                extra_body={
                    "provider": {"sort": "throughput"},
                    "reasoning": {"max_tokens": 50}
                },
                timeout=60.0
            )
            break
        except Exception as e:
            last_err = e
            time.sleep(2)
            
    t1 = time.perf_counter()
    if resp is None:
        raise last_err or Exception("Không nhận được phản hồi")
        
    prompt_tokens = getattr(resp.usage, 'prompt_tokens', 0) or 0
    comp_tokens = getattr(resp.usage, 'completion_tokens', 0) or 0
    return {
        "worker_id": worker_id,
        "duration": t1 - t0,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": comp_tokens,
        "lines": len(chunk)
    }

def run_benchmark_for_concurrency(client, model, concurrency, chunk_size=70):
    total_lines = concurrency * chunk_size
    chunks = [generate_chunk(chunk_size, start_id=i * chunk_size + 1) for i in range(concurrency)]
    print(f"\n>>> [Concurrency {concurrency}] Đang dịch {concurrency} chunks ({total_lines} câu) với {concurrency} luồng song song...", flush=True)
    start_wall = time.perf_counter()
    
    total_prompt_tok = 0
    total_comp_tok = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(translate_chunk, client, model, chunk, i + 1) for i, chunk in enumerate(chunks)]
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            total_prompt_tok += res["prompt_tokens"]
            total_comp_tok += res["completion_tokens"]
            print(f"  [Luồng #{res['worker_id']}] Xong {res['lines']} câu trong {res['duration']:.2f}s | Output: {res['completion_tokens']} tokens", flush=True)
            
    total_wall = time.perf_counter() - start_wall
    subs_per_sec = total_lines / total_wall if total_wall > 0 else 0
    print(f"  -> Concurrency {concurrency} hoàn thành trong: {total_wall:.2f}s (Tốc độ: {subs_per_sec:.2f} câu/giây)", flush=True)
    
    return {
        "concurrency": concurrency,
        "subtitles": total_lines,
        "chunks": concurrency,
        "wall_time": round(total_wall, 2),
        "subs_per_sec": round(subs_per_sec, 2),
        "prompt_tokens": total_prompt_tok,
        "completion_tokens": total_comp_tok
    }

def main():
    api_key, base_url, model = load_credentials()
    print("==================================================", flush=True)
    print("         NOVACUT BENCHMARK TRANSLATION PIPELINE", flush=True)
    print(f"Model: {model}", flush=True)
    print(f"Base URL: {base_url}", flush=True)
    print(f"Chunk Size: 70 subtitles", flush=True)
    print(f"OpenRouter Provider Routing: throughput", flush=True)
    print("==================================================", flush=True)
    
    if not api_key or api_key.startswith('•'):
        print("Lỗi: Không tìm thấy API Key hợp lệ.", flush=True)
        return
        
    client = openai.OpenAI(
        api_key=api_key,
        base_url=base_url,
        default_headers={"HTTP-Referer": "https://novacut.app", "X-Title": "NovaCut AI"},
        timeout=60.0
    )
    
    concurrency_levels = [1, 4, 6, 8]
    results = []
    
    for c in concurrency_levels:
        try:
            r = run_benchmark_for_concurrency(client, model, c, chunk_size=70)
            results.append(r)
        except Exception as e:
            print(f"Lỗi khi benchmark concurrency {c}: {e}", flush=True)
            
    print("\n" + "=" * 76, flush=True)
    print("    BẢNG TỔNG KẾT BENCHMARK QWEN3.7 FLASH TRÊN OPENROUTER", flush=True)
    print("=" * 76, flush=True)
    print(f"{'Concurrency':<12} | {'Subtitles':<10} | {'Wall Time (s)':<14} | {'Subtitles/sec':<14} | {'Tokens':<10}", flush=True)
    print("-" * 76, flush=True)
    for r in results:
        tot_tok = r['prompt_tokens'] + r['completion_tokens']
        print(f"{r['concurrency']:<12} | {r['subtitles']:<10} | {r['wall_time']:<14} | {r['subs_per_sec']:<14} | {tot_tok:<10}", flush=True)
    print("=" * 76, flush=True)

if __name__ == '__main__':
    main()
