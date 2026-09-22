"""Dependency-free regression tests; decoding and recognition are deliberately mocked."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ocr_under_test', ROOT / 'ocr_module.py')
ocr = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'cv2': types.ModuleType('cv2'), 'numpy': types.ModuleType('numpy'), 'torch': None}):
    spec.loader.exec_module(ocr)


class Image:
    def __init__(self, value):
        self.value = value

    def __getitem__(self, key):
        # Top and bottom region carry distinct text.
        return Image(self.value + ('A' if key[0].start == 0 else 'B'))

    def copy(self):
        return self


class Capture:
    def __init__(self):
        self.position = 0
        self.released = False

    def isOpened(self):
        return True

    def grab(self):
        self.position += 1
        return True

    def read(self):
        frame = Image(str(self.position // 2))
        self.position += 1
        return True, frame

    def release(self):
        self.released = True


class OCRTests(unittest.TestCase):
    def test_real_rapidocr_detector_infer_layout(self):
        session = types.SimpleNamespace(get_providers=lambda: ['DmlExecutionProvider', 'CPUExecutionProvider'])
        wrapper = types.SimpleNamespace(session=session)
        engine = types.SimpleNamespace(text_det=types.SimpleNamespace(infer=wrapper),
                                       text_rec=types.SimpleNamespace(session=wrapper))
        providers = ocr._engine_providers(engine)
        self.assertTrue(all('DmlExecutionProvider' in value for value in providers.values()))

    def test_gpu_detector_infer_is_not_discarded(self):
        session = types.SimpleNamespace(get_providers=lambda: ['DmlExecutionProvider'])
        wrapper = types.SimpleNamespace(session=session)
        engine = types.SimpleNamespace(text_det=types.SimpleNamespace(infer=wrapper),
                                       text_rec=types.SimpleNamespace(session=wrapper))
        from unittest.mock import Mock
        make = Mock(return_value=engine)
        with patch.dict(sys.modules, {
            'rapidocr_onnxruntime': types.SimpleNamespace(RapidOCR=make),
            'onnxruntime': types.SimpleNamespace(get_available_providers=lambda: ['DmlExecutionProvider', 'CPUExecutionProvider'])
        }):
            actual, provider = ocr._make_extract_engine('cuda', 2)
        self.assertIs(actual, engine)
        self.assertEqual(provider, 'DmlExecutionProvider')
        self.assertEqual(make.call_count, 1)

    def test_regions_validation(self):
        good = dict(x=0, y=0, w=100, h=10)
        self.assertEqual(ocr.normalize_ocr_regions(good)[0]['label'], 'Phụ đề')
        for bad in [[], [good]*9, None, dict(good, x=float('nan')), dict(good, x=1), dict(good, w=0)]:
            with self.assertRaises((ValueError, TypeError)):
                ocr.normalize_ocr_regions(bad)

    def test_merge_preserves_empty_gap_and_clamps_end(self):
        merged = ocr._merge_ocr_samples([(0, '甲'), (.5, '甲'), (1, ''), (1.5, '甲'), (2, '乙')], .5, 2.2)
        self.assertEqual(merged, [dict(start=0, end=1, text='甲'), dict(start=1.5, end=2, text='甲'), dict(start=2, end=2.2, text='乙')])

    def test_gpu_silent_fallback_tries_next_provider(self):
        made = []
        def make(**kwargs):
            made.append(kwargs)
            provider = 'CUDAExecutionProvider' if kwargs.get('det_use_cuda') else 'CPUExecutionProvider'
            session = types.SimpleNamespace(get_providers=lambda: [provider])
            sub = types.SimpleNamespace(session=types.SimpleNamespace(session=session))
            return types.SimpleNamespace(text_det=sub, text_rec=sub)
        with patch.dict(sys.modules, {
            'rapidocr_onnxruntime': types.SimpleNamespace(RapidOCR=make),
            'onnxruntime': types.SimpleNamespace(get_available_providers=lambda: ['DmlExecutionProvider', 'CUDAExecutionProvider'])
        }):
            _, provider = ocr._make_extract_engine('auto', 4)
        self.assertEqual(provider, 'CUDAExecutionProvider')
        self.assertEqual(len(made), 2)
        self.assertEqual(made[-1]['intra_op_num_threads'], 4)

    def run_scan(self, directory, stop=None, fail=False):
        cap = Capture()
        cv = types.SimpleNamespace(VideoCapture=lambda _: cap, COLOR_BGR2GRAY=1,
                                   cvtColor=lambda image, _: image,
                                   absdiff=lambda a, b: types.SimpleNamespace(max=lambda: 0 if a.value == b.value else 255))
        def engine(image, **kwargs):
            if fail:
                raise RuntimeError('inference failed')
            return [([], image.value, .99)], None
        with patch.object(ocr, 'cv2', cv), patch.object(ocr, '_make_extract_engine', return_value=(engine, 'CPUExecutionProvider')), patch.object(ocr, 'get_video_info', return_value=(100, 100, 4, 9, 2.25)), patch.object(ocr, 'is_blank_or_no_text', return_value=False):
            events = list(ocr.process_ocr(str(Path(directory)/'movie.mp4'), [dict(x=0, y=0, w=100, h=10), dict(x=0, y=50, w=100, h=10, label='人物')], check_stop=stop))
        return cap, events

    def test_multiregion_outputs_and_shared_decode(self):
        with tempfile.TemporaryDirectory() as directory:
            cap, events = self.run_scan(directory)
            data = json.loads((Path(directory)/'movie_ocr_regions.json').read_text(encoding='utf-8'))
            self.assertEqual(len(data['tracks']), 2)
            self.assertEqual(data['tracks'][1]['region']['label'], '人物')
            self.assertTrue(data['tracks'][0]['segments'][0]['text'].endswith('A'))
            self.assertTrue(data['tracks'][1]['segments'][0]['text'].endswith('B'))
            self.assertEqual(data['tracks'][0]['segments'][-1]['end'], 2.25)
            self.assertTrue((Path(directory)/'movie_ocr_region_2.srt').exists())
            self.assertTrue(events[-1].strip().endswith('_ocr.srt'))
            self.assertEqual(cap.position, 9)
            self.assertTrue(cap.released)

    def test_cancel_does_not_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            cap, _ = self.run_scan(directory, stop=lambda: True)
            self.assertEqual(list(Path(directory).iterdir()), [])
            self.assertTrue(cap.released)

    def test_inference_failure_does_not_publish_empty_subtitles(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, 'inference failed'):
                self.run_scan(directory, fail=True)
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
