with open('ai33_pricing_dump.txt', 'r', encoding='utf-8') as f:
    content = f.read()

out_blocks = []
for block in content.split('---'):
    if any(k in block.lower() for k in ['tts', 'speech', 'character', 'cost', 'pricing', 'multiplier', 'plans']):
        out_blocks.append(block.strip()[:400])

with open('scratch_filtered_utf8.txt', 'w', encoding='utf-8') as f:
    for b in out_blocks:
        f.write(b + "\n" + "="*50 + "\n")

print(f"Wrote {len(out_blocks)} blocks")
