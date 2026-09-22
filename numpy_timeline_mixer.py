"""
numpy_timeline_mixer.py - High-Performance Block-Based Timeline Audio Mixer
Replaces slow Python-level sample loops with vectorized NumPy additions
and windowed block-based memory management for arbitrary long timelines.
"""

import os
import wave
import math
import numpy as np
from typing import List, Tuple, Optional, Callable


def get_audio_clip_info(wav_path: str) -> Tuple[int, int, int, float]:
    """Returns (channels, sampwidth, framerate, duration_seconds) for a WAV file."""
    with wave.open(wav_path, 'rb') as wf:
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        sr = wf.getframerate()
        n_frames = wf.getnframes()
        dur = n_frames / float(sr) if sr > 0 else 0.0
        return ch, sw, sr, dur


def mix_timeline_clips(
    clips: List[Tuple[str, float]],
    output_path: str,
    target_sample_rate: int = 44100,
    target_channels: int = 2,
    min_total_duration: float = 0.0,
    block_duration_sec: float = 60.0,
    progress_cb: Optional[Callable[[float], None]] = None
) -> str:
    """
    Mixes a collection of (wav_file_path, start_seconds) onto a single master timeline.
    
    Uses block-based processing for long timelines to keep peak RAM usage under ~50MB,
    with vectorized NumPy additions and int16 saturation clipping [-32767, 32767].
    
    Args:
        clips: List of tuples (wav_path, start_seconds)
        output_path: Destination WAV file path
        target_sample_rate: Output audio sample rate (default 44100)
        target_channels: Output channels (default 2 for stereo)
        min_total_duration: Minimum total duration of the master track
        block_duration_sec: Duration of each chunk block in seconds (default 60s)
        progress_cb: Optional callback(pct_0_to_100)
        
    Returns:
        Absolute path to generated output_path
    """
    if not clips:
        # Create silent track
        total_dur = max(min_total_duration, 1.0)
        total_samples = int(total_dur * target_sample_rate)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with wave.open(output_path, 'wb') as wf:
            wf.setnchannels(target_channels)
            wf.setsampwidth(2)
            wf.setframerate(target_sample_rate)
            silent = np.zeros((total_samples, target_channels), dtype=np.int16)
            wf.writeframes(silent.tobytes())
        return output_path

    # 1. Index all clips: compute (start_s, end_s, start_sample, end_sample, path)
    clip_records = []
    max_end_time = 0.0

    for path, start_s in clips:
        if not os.path.exists(path) or os.path.getsize(path) < 44:
            continue
        try:
            with wave.open(path, 'rb') as wf:
                sr = wf.getframerate()
                n_frames = wf.getnframes()
                dur = n_frames / float(sr) if sr > 0 else 0.0
                end_s = start_s + dur
                max_end_time = max(max_end_time, end_s)
                clip_records.append({
                    "path": path,
                    "start_s": float(start_s),
                    "end_s": float(end_s),
                    "duration_s": dur,
                    "sr": sr,
                    "channels": wf.getnchannels(),
                    "sampwidth": wf.getsampwidth(),
                    "frames": n_frames
                })
        except Exception as e:
            print(f"[Mixer] Warning: skipping invalid clip {path}: {e}")

    if not clip_records:
        raise ValueError("Không có clip âm thanh hợp lệ để ghép timeline.")

    final_duration = max(max_end_time, float(min_total_duration))
    total_samples = int(math.ceil(final_duration * target_sample_rate))

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # 2. Fast Path: If total timeline <= block_duration_sec, mix in a single in-memory array
    if final_duration <= block_duration_sec:
        master_buffer = np.zeros((total_samples, target_channels), dtype=np.int32)
        for c in clip_records:
            _overlay_clip_into_array(c, master_buffer, target_sample_rate, target_channels, 0.0)

        clipped = np.clip(master_buffer, -32767, 32767).astype(np.int16)
        with wave.open(output_path, 'wb') as wf:
            wf.setnchannels(target_channels)
            wf.setsampwidth(2)
            wf.setframerate(target_sample_rate)
            wf.writeframes(clipped.tobytes())

        if progress_cb:
            progress_cb(100.0)
        return output_path

    # 3. Block-Based Processing for arbitrary long timelines (e.g. 1-3 hours)
    block_samples = int(block_duration_sec * target_sample_rate)
    total_blocks = int(math.ceil(total_samples / float(block_samples)))

    with wave.open(output_path, 'wb') as wf:
        wf.setnchannels(target_channels)
        wf.setsampwidth(2)
        wf.setframerate(target_sample_rate)

        for b_idx in range(total_blocks):
            b_start_sample = b_idx * block_samples
            b_end_sample = min(b_start_sample + block_samples, total_samples)
            curr_block_len = b_end_sample - b_start_sample

            b_start_s = b_start_sample / float(target_sample_rate)
            b_end_s = b_end_sample / float(target_sample_rate)

            # Block accumulator in 32-bit int to prevent overflow
            block_buf = np.zeros((curr_block_len, target_channels), dtype=np.int32)

            # Find all clips that intersect this block [b_start_s, b_end_s)
            intersecting = [
                c for c in clip_records
                if c["start_s"] < b_end_s and c["end_s"] > b_start_s
            ]

            for c in intersecting:
                _overlay_clip_into_array(
                    c, block_buf, target_sample_rate, target_channels, b_start_s
                )

            # Clip and write
            clipped_block = np.clip(block_buf, -32767, 32767).astype(np.int16)
            wf.writeframes(clipped_block.tobytes())

            if progress_cb:
                pct = ((b_idx + 1) / float(total_blocks)) * 100.0
                progress_cb(pct)

    return output_path


def _overlay_clip_into_array(
    clip: dict,
    target_arr: np.ndarray,
    target_sr: int,
    target_ch: int,
    block_start_s: float
):
    """Reads a WAV clip and adds its samples to target_arr at the proper offset."""
    try:
        with wave.open(clip["path"], 'rb') as wf:
            raw = wf.readframes(clip["frames"])
            src_sw = clip["sampwidth"]
            src_ch = clip["channels"]
            src_sr = clip["sr"]

            # Parse PCM
            if src_sw == 2:
                samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            elif src_sw == 4:
                samples = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 65536.0
            elif src_sw == 1:
                samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) * 256.0
            else:
                return

            if src_ch > 1:
                samples = samples.reshape(-1, src_ch)
            else:
                samples = samples.reshape(-1, 1)

            # Convert channel count if needed
            if src_ch == 1 and target_ch == 2:
                samples = np.repeat(samples, 2, axis=1)
            elif src_ch > target_ch:
                samples = samples[:, :target_ch]

            # Resample if sample rate doesn't match
            if src_sr != target_sr and len(samples) > 0:
                import scipy.signal
                new_len = int(round(len(samples) * target_sr / float(src_sr)))
                samples = scipy.signal.resample(samples, new_len, axis=0)

            # Target placement relative to block_start_s
            clip_start_s = clip["start_s"]
            offset_in_block_s = clip_start_s - block_start_s

            target_start_idx = int(round(offset_in_block_s * target_sr))
            target_end_idx = target_start_idx + len(samples)

            # Intersection between [target_start_idx, target_end_idx) and [0, len(target_arr))
            arr_len = len(target_arr)
            src_start = max(0, -target_start_idx)
            src_end = len(samples) - max(0, target_end_idx - arr_len)

            dst_start = max(0, target_start_idx)
            dst_end = min(arr_len, target_end_idx)

            if dst_end > dst_start and src_end > src_start:
                slice_len = min(dst_end - dst_start, src_end - src_start)
                target_arr[dst_start:dst_start + slice_len] += samples[src_start:src_start + slice_len].astype(np.int32)
    except Exception as ex:
        print(f"[Mixer] Error overlaying clip {clip.get('path')}: {ex}")
