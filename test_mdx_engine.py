import os
import sys
import torch
import numpy as np
import mdx_separator

print("[Test] Testing MDX-NET Engine...")
model_name = "UVR-MDX-NET-Inst_HQ_4.onnx"
session = mdx_separator.get_mdx_session(model_name)
print(f"[Test] Session initialized successfully! Providers: {session.get_providers()}")

# Create dummy audio tensor (2 channels, 44100 * 3 samples = 3 seconds)
sr = 44100
t = np.linspace(0, 3, sr * 3, dtype=np.float32)
# Mix sine wave (vocals 1kHz + bgm 200Hz)
sig1 = 0.5 * np.sin(2 * np.pi * 1000 * t) + 0.3 * np.sin(2 * np.pi * 200 * t)
sig2 = 0.5 * np.sin(2 * np.pi * 1000 * t) + 0.3 * np.sin(2 * np.pi * 200 * t)
dummy_wav = np.stack([sig1, sig2])

temp_dir = os.path.join(mdx_separator.ROOT_DIR, "output", "test_mdx")
os.makedirs(temp_dir, exist_ok=True)
dummy_input = os.path.join(temp_dir, "dummy_input.wav")

import torchaudio
torchaudio.save(dummy_input, torch.tensor(dummy_wav), sr)
print(f"[Test] Saved dummy audio to {dummy_input}")

res = mdx_separator.separate_stems_mdx(
    dummy_input,
    temp_dir,
    model_name=model_name,
    progress_cb=lambda p, m: print(f"Progress: {p}% - {m}")
)

print("[Test] Result:", res)
assert os.path.exists(res["instrumental_path"]), "Instrumental file not found"
assert os.path.exists(res["vocals_path"]), "Vocals file not found"
print("[Test] ✅ MDX-NET Inst HQ4 Test Passed 100%!")
