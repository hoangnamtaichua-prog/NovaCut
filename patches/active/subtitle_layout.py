"""Write positioned subtitles using the editor's percentage geometry."""
import math
import re


def write_positioned_ass(source, destination, region, align='center'):
    def number(key, default):
        try:
            value = float(region.get(key, default))
            return value if math.isfinite(value) else default
        except (TypeError, ValueError):
            return default

    x = max(0, min(99, number('x', 20)))
    y = max(0, min(99, number('y', 81.5)))
    w = max(1, min(100 - x, number('w', 60)))
    h = max(1, min(100 - y, number('h', 9.5)))
    anchor = {'left': 4, 'center': 5, 'right': 6}.get(align, 5)
    px = (x + (0 if anchor == 4 else w if anchor == 6 else w / 2)) * 3.84
    py = (y + h / 2) * 2.88
    left, right = round(x * 3.84), round((100 - x - w) * 3.84)
    header = '[Script Info]\nScriptType: v4.00+\nPlayResX: 384\nPlayResY: 288\nWrapStyle: 0\n\n'
    header += '[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
    header += 'Style: Default,Arial,24,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,5,0,0,0,1\n\n'
    header += '[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
    with open(source, encoding='utf-8-sig') as stream:
        srt = stream.read().replace('\r\n', '\n')
    pattern = r'(\d+):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d+):(\d{2}):(\d{2})[,.](\d{3})[^\n]*\n(.*?)(?=\n\s*\n|\Z)'
    def stamp(parts):
        hour, minute, second, millis = map(int, parts)
        return f'{hour}:{minute:02}:{second:02}.{millis // 10:02}'
    lines = []
    for match in re.finditer(pattern, srt, re.S):
        fields = match.groups()
        text = re.sub(r'<[^>]*>', '', fields[8]).strip()
        text = text.replace('\\', '＼').replace('{', '｛').replace('}', '｝').replace('\n', r'\N')
        tags = rf'{{\an{anchor}\pos({px:.3f},{py:.3f})\fscx{max(10, w / 60 * 100):.3f}\fscy{max(10, h / 9.5 * 100):.3f}}}'
        lines.append(f'Dialogue: 0,{stamp(fields[:4])},{stamp(fields[4:8])},Default,,{left},{right},0,,{tags}{text}\n')
    if not lines:
        raise ValueError('Không đọc được phụ đề để áp dụng khung chữ đã chỉnh.')
    with open(destination, 'w', encoding='utf-8') as stream:
        stream.write(header + ''.join(lines))
    return destination
