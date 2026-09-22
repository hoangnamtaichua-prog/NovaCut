"""Synthetic mixer-only benchmark; does not load models or change app files."""
import array
import json
import statistics
import time

import numpy as np


def legacy(clip, count):
    master = array.array('h', [0]) * len(clip)
    for _ in range(count):
        for index, sample in enumerate(clip):
            master[index] = max(-32767, min(32767, master[index] + sample))
    return master


def vectorized(clip, count):
    master = np.zeros(len(clip), dtype=np.int16)
    source = np.frombuffer(clip, dtype=np.int16).astype(np.int32)
    for _ in range(count):
        mixed = master.astype(np.int32) + source
        master[:] = np.clip(mixed, -32767, 32767)
    return master


def main():
    rng = np.random.default_rng(20260917)
    clip = array.array('h')
    clip.frombytes(rng.integers(-25000, 25001, size=44100 * 2 * 10, dtype=np.int16).tobytes())
    measurements = {}
    outputs = {}
    for name, function in [('legacy', legacy), ('numpy', vectorized)]:
        times = []
        for _ in range(3):
            start = time.perf_counter()
            outputs[name] = function(clip, 3)
            times.append(time.perf_counter() - start)
        measurements[name] = {'seconds': times, 'median_seconds': statistics.median(times)}
    equal = np.array_equal(np.frombuffer(outputs['legacy'], dtype=np.int16), outputs['numpy'])
    assert equal
    print(json.dumps({'scope': 'Synthetic PCM overlay only; three overlapping 10-second stereo clips; excludes disk I/O and TTS', 'sample_rate': 44100, 'channels': 2, 'numpy_version': np.__version__, 'pcm_exact_equal': bool(equal), 'measurements': measurements, 'median_speedup': measurements['legacy']['median_seconds'] / measurements['numpy']['median_seconds']}, indent=2))


if __name__ == '__main__':
    main()
