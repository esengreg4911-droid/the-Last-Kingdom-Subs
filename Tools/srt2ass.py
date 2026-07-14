# -*- coding: utf-8 -*-
import sys, re, io

def is_cjk(s):
    for ch in s:
        o = ord(ch)
        if (0x4E00 <= o <= 0x9FFF) or (0x3400 <= o <= 0x4DBF) or \
           (0x3000 <= o <= 0x303F) or (0xFF00 <= o <= 0xFFEF):
            return True
    return False

def conv_time(t):
    # 00:00:08,200 -> 0:00:08.20
    t = t.strip()
    m = re.match(r'(\d+):(\d+):(\d+)[,.](\d+)', t)
    h, mm, ss, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    cs = round(ms / 10.0)
    if cs > 99:
        cs = 99
    return "%d:%02d:%02d.%02d" % (h, mm, ss, cs)

def build_text(lines):
    out = []
    for ln in lines:
        if ln == "":
            out.append("")
        elif is_cjk(ln):
            out.append(r"{\rChinese}" + ln)   # switch to Chinese style
        else:
            out.append(r"{\rEnglish}" + ln)   # switch to English style
    return r"\N".join(out)

src = sys.argv[1]
dst = sys.argv[2]

with io.open(src, "r", encoding="utf-8-sig") as f:
    content = f.read()
content = content.replace("\r\n", "\n").replace("\r", "\n")

# split into blocks on blank lines
raw_blocks = re.split(r"\n\s*\n", content)

events = []
for blk in raw_blocks:
    blk_lines = blk.split("\n")
    while blk_lines and blk_lines[0].strip() == "":
        blk_lines.pop(0)
    if not blk_lines:
        continue
    time_idx = None
    for i, l in enumerate(blk_lines):
        if "-->" in l:
            time_idx = i
            break
    if time_idx is None:
        continue
    tparts = blk_lines[time_idx].split("-->")
    start = conv_time(tparts[0])
    end = conv_time(tparts[1])
    text_lines = [l.rstrip() for l in blk_lines[time_idx + 1:]]
    while text_lines and text_lines[-1] == "":
        text_lines.pop()
    text = build_text(text_lines)
    events.append((start, end, text))

header = r"""[Script Info]
Title: Styled Subtitle
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Chinese,Microsoft YaHei,55,&H00E0F2F8,&H000000FF,&H0010161F,&H64000000,0,0,0,0,100,100,0,0,1,2,1,2,120,120,60,1
Style: English,Times New Roman,40,&H00A8D6E6,&H000000FF,&H0010161F,&H64000000,0,0,0,0,100,100,0,0,1,2,1,2,120,120,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

lines_out = [header]
for start, end, text in events:
    lines_out.append("Dialogue: 0,%s,%s,Chinese,,0,0,0,,%s" % (start, end, text))

with io.open(dst, "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines_out) + "\n")

print("blocks:", len(events))
