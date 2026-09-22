import ast, array, concurrent.futures, hashlib, os, shutil, subprocess, sys, tempfile, time, types, wave
from pathlib import Path
from unittest.mock import patch
root = Path.cwd()
source = ast.parse((root/'ai_dubbing.py').read_text(encoding='utf-8'))
functions = [n for n in source.body if isinstance(n, ast.FunctionDef) and n.name in ('parse_time_str','build_dubbing_track_for_subtitles_generator')]
with tempfile.TemporaryDirectory(dir='scratch') as folder:
    def synth(text, voice, speed, output, key):
        with wave.open(output,'wb') as wav:
            wav.setparams((2,2,44100,0,'NONE','not compressed'))
            wav.writeframes(array.array('h',[100]) * (44100*2*9))
    scope = dict(globals(), ROOT_DIR=folder, synthesize_sentence=synth,
        ffmpeg_installer=types.SimpleNamespace(ensure_ffmpeg=lambda: str(root/'bin/ffmpeg.exe'),get_stealth_subprocess_kwargs=lambda:{}))
    exec(compile(ast.Module(body=functions,type_ignores=[]),'ai_dubbing.py','exec'),scope)
    with patch.dict(sys.modules, {'custom_voices':types.SimpleNamespace(get_voice_by_id=lambda _:None)}):
        events=list(scope['build_dubbing_track_for_subtitles_generator']([{'text':'test','startSeconds':1,'endSeconds':3}], 'local_test',1.0,folder))
    with wave.open(events[-1][1],'rb') as wav:
        assert wav.getnframes() == 441000, wav.getnframes()
        wav.setpos(441000-1)
        assert array.array('h',wav.readframes(1))[0] == 100
print('PASS: shared export/preview mixer retains 9-second sentence to its final sample')
