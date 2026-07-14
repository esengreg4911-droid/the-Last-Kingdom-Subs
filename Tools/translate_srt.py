# -*- coding: utf-8 -*-
"""
translate_srt.py — 《孤国春秋》(The Last Kingdom) 字幕双语本地化翻译工具

功能:
  - 解析 SRT 字幕, 逐条调用 LLM 翻译成中文
  - 输出双语对照字幕: 中文在上, 英文原文在下
  - 时间戳与行号原样保留, 绝不改动
  - 维护持久化术语表 glossary.json, 跨集统一人名/地名/专名
  - 支持整季批量翻译

接口: OpenAI 兼容 (OpenAI / DeepSeek / 智谱GLM / 各类中转或本地服务均可)

用法:
  1. 安装依赖:   pip install openai
  2. 设置环境变量 (PowerShell):
        $env:LLM_API_KEY  = "你的key"
        $env:LLM_BASE_URL = "https://api.deepseek.com"      # 按你的服务改
        $env:LLM_MODEL    = "deepseek-chat"                 # 按你的服务改
  3. 翻单个文件:
        python translate_srt.py "the.last.kingdom.s01e01....srt"
  4. 批量翻整季 (当前目录所有 .srt):
        python translate_srt.py --batch .

输出文件名: 原名去掉 .srt 后加 .zh-en.srt
"""

import os
import re
import sys
import json
import time
import argparse

try:
    from openai import OpenAI
except ImportError:
    sys.exit("缺少依赖, 请先运行: pip install openai")


# ----------------------------------------------------------------------------
# 翻译风格规则 (作为 system prompt 的核心, 决定翻译质量)
# ----------------------------------------------------------------------------
STYLE_RULES = """你是一位殿堂级的影视翻译家兼历史学家, 极其擅长中英双语影视字幕的本地化翻译。
你正在翻译英国历史史诗美剧《孤国春秋》(The Last Kingdom) 的英文字幕。

# 背景
本剧讲述 9 世纪英格兰维京时代, 撒克逊人(基督教徒)与丹麦维京人(北欧多神教徒)之间的战争与信仰冲突。
主角是贝班堡的乌特雷德 (Uhtred of Bebbanburg)。

# 翻译风格要求
1. 语气基调: 庄重、有历史厚重感, 但必须是【自然、口语化、能顺口念出来的现代白话】,
   不是文言文, 不是书面古文。要像一个古代战士/贵族在真实开口说话, 而不是在念史书。
   - 严禁文言腔和拗口的书面语。反例(不要这样): "它以我们的血与骨得以巩固""与你叔父同在,
     我负责保护你的安全""你若想上阵, 便与我掰腕子""汝""吾""者也""之乎"。
   - 正例(应该这样): "这片土地是我们用血肉打下来的""你跟你叔父留在这儿, 我来保护你,
     你要是想打架, 就跟我掰手腕"。
   - 判断标准: 译文读起来要顺口、像人话; 若一句话需要停下来琢磨才懂, 就是太文了, 改白。
   - 严禁现代网络流行语和现代政治/商业术语(如"领导""下属""汇报""搞定""点赞""内卷"等)。
2. 宫廷得体: 贵族/宫廷对话可以稍正式, 但仍要自然。"My Lord"译"大人"或"领主";
   "Your Majesty"译"陛下"; "swear an oath"译"宣誓效忠"(不要写成"立下誓言"这种腔调时用自然说法)。
3. 信仰对立:
   - 撒克逊/基督教阵营: 用虔诚基督教词汇。"God"/"Lord"译"天主/主"; "Pagan/Heathen"译"异教徒";
     "Priest"译"神父/教士"。
   - 维京/丹麦阵营: 用北欧多神教词汇。"The Gods"译"众神"; "Valhalla"译"英灵殿"; "Odin"译"奥丁";
     "Thor"译"托尔"。
4. 战士粗粝与战友情: 战士对话粗犷、直接、豪爽, 带战场泥土味。"Arseling"译"浑球"或"蠢货";
   战场喊话简短有力, "Shield wall!"译"立盾墙!"。
5. 经典台词与专名统一:
   - "Destiny is all" 统一译"命运主宰一切"。
   - "ealdorman" 译"郡长"或"领主", 【绝不能译成"郡主"】(郡主指郡王之女, 是女性, 意思完全错误)。
   - 其余专有名词严格按下方提供的术语表翻译, 保持全季一致。

# 翻译规则 (务必遵守)
- 只翻译台词内容本身, 不要输出任何解释、注释或额外文字。
- 【括号内容一律不翻译】: 像 (LORD UHTRED)、(BEOCCA)、(GRUNTING)、(MEN CHEERING) 这类
  圆括号或方括号里的说话人标记、音效提示, 全部忽略, 不要出现在中文译文里。
  只翻译括号之外的真正台词。若整条只有括号内容, 则中文译文返回空字符串 ""。
- 【标点用中文全角符号】: 中文译文句中的标点一律使用中文全角符号
  (逗号 "，"、问号 "？"、感叹号 "！"、顿号 "、"、冒号 "："、分号 "；"、省略号 "……"),
  不要使用英文半角标点。
- 【不要用句号】: 中文译文结尾和句中都不要使用句号 "。"。陈述句直接结束即可。
  中文译文的【结尾】也不要出现逗号 "，", 句子直接收住即可。
- 【不要有多余空格】: 中文译文里不要出现多余的空格, 中文文字与标点之间紧挨着写。
- 【全部合并为一行】: 无论英文原文有几行, 中文译文都合并成一行输出, 绝不换行。
  即使原文是两个不同的人的对话 (多行都以 "- " 破折号开头),
  中文也要铺成一行, 用 " - " 分隔不同说话人的话, 不要分成多行。
- 保留 HTML 标签(如 <i>、<font ...>)在中文译文里的对应位置。
- 遇到无法确定含义的专有名词, 采用音译并保持前后一致。
"""

GLOSSARY_INSTRUCTION = """
# 当前术语表 (必须严格遵守, 保证全季统一)
{glossary}

# 输出格式 (极其重要)
你会收到一个 JSON 数组, 每个元素是 {{"id": 序号, "en": "英文原文(可能含\\n多行)"}}。
请返回一个 JSON 数组, 每个元素是 {{"id": 序号, "zh": "中文译文(务必合并成一行, 不含任何换行符)"}}。
只返回 JSON, 不要有任何其他文字或 markdown 代码块标记。
如果你在翻译中确认了新的专有名词译法(术语表里没有的人名/地名), 额外在返回中加一个
{{"id": -1, "new_terms": {{"英文专名": "中文译法"}}}} 元素。
"""

# ----------------------------------------------------------------------------
# SRT 解析 / 生成
# ----------------------------------------------------------------------------
TIMECODE_RE = re.compile(r"^\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}")


class Cue:
    __slots__ = ("index", "timecode", "text_lines")

    def __init__(self, index, timecode, text_lines):
        self.index = index
        self.timecode = timecode
        self.text_lines = text_lines  # list[str]

    @property
    def text(self):
        return "\n".join(self.text_lines)


def parse_srt(path):
    """把 srt 解析成 Cue 列表。兼容 BOM 和 CRLF/LF。"""
    with open(path, "r", encoding="utf-8-sig") as f:
        content = f.read()
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", content)
    cues = []
    for block in blocks:
        lines = block.split("\n")
        # 去掉尾部空行
        while lines and lines[-1].strip() == "":
            lines.pop()
        if not lines:
            continue
        # 找时间戳所在行
        tc_idx = None
        for i, ln in enumerate(lines):
            if TIMECODE_RE.match(ln.strip()):
                tc_idx = i
                break
        if tc_idx is None:
            continue  # 不是有效字幕块, 跳过
        index = lines[tc_idx - 1].strip() if tc_idx >= 1 else ""
        timecode = lines[tc_idx].strip()
        text_lines = lines[tc_idx + 1:]
        # 过滤字幕组署名/水印块 (如 "Fixed & Synced By ..."), 无功能作用
        joined = " ".join(text_lines)
        if re.search(r"(fixed|synced|sync|subtitle|translated|encoded|ripped|resync)\s*(&|and|by)?",
                     joined, re.IGNORECASE) and "-->" not in joined:
            plain = re.sub(r"<[^>]+>", "", joined)
            if re.search(r"\bby\b", plain, re.IGNORECASE):
                continue  # 跳过署名块, 不写入输出
        cues.append(Cue(index, timecode, text_lines))
    return cues


def is_pure_sound_cue(text):
    """整条只是音效/占位提示 (如 (GRUNTING)), 可跳过 LLM 直接原样标注。"""
    stripped = text.strip()
    if not stripped:
        return True
    # 全部内容都被圆括号包裹且大写为主, 视为纯音效
    return bool(re.fullmatch(r"[\(\[].*[\)\]]", stripped)) and not any(
        c.islower() for c in re.sub(r"[\(\)\[\]]", "", stripped)
    )


def strip_brackets(text):
    """删除英文原文里的括号标记(说话人/音效), 只留真正台词。用于英文行也一并清理。"""
    text = re.sub(r"[\(\[][^\)\]]*[\)\]]", "", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip(" \t-")


def has_translatable_text(text):
    """去掉所有括号标记后, 是否仍有真正需要翻译的字母台词。
    用于校验: 有实际台词却漏翻(中文为空)的条目需要补翻。"""
    core = strip_brackets(text)
    # 去掉纯符号/破折号/省略号后, 还剩字母才算有台词
    core = re.sub(r"[\-—…\.\s]", "", core)
    return bool(re.search(r"[A-Za-z]", core))


def clean_zh(zh):
    """对模型返回的中文译文做保底清洗:
    1. 去掉残留的括号内容 (说话人/音效)
    2. 去掉中文句号 (含全角 。 和用于句尾的英文 .)
    3. 无论原文几行、是否对话, 全部合并成一行
    4. 句中标点统一为中文全角, 去掉多余空格
    5. 去掉结尾的逗号
    """
    if not zh:
        return ""
    lines = [ln.strip() for ln in zh.split("\n")]
    lines = [ln for ln in lines if ln]

    # 是否为多人对话 (至少两行以 - 开头): 合并成一行, 用 " - " 分隔
    dash_lines = [ln for ln in lines if ln.startswith("-")]
    is_dialogue = len(dash_lines) >= 2

    def scrub(s):
        s = re.sub(r"[\(（【\[][^\)）】\]]*[\)）】\]]", "", s)  # 去括号内容
        s = s.replace("。", "")                                  # 去全角句号
        s = re.sub(r"(?<![\.\d])\.(?=\s|$)", "", s)              # 去英文句尾点(不动省略号/小数)
        # 句中英文半角标点转中文全角 (不动千分位数字 1,000)
        s = re.sub(r",(?!\d)", "，", s)                          # 逗号
        s = re.sub(r"\?", "？", s)                               # 问号
        s = re.sub(r"!", "！", s)                                # 感叹号
        s = re.sub(r"[ \t]+", "", s)                             # 去掉所有多余空格
        return s.strip()

    if is_dialogue:
        parts = []
        for ln in lines:
            core = ln[1:].strip() if ln.startswith("-") else ln
            core = scrub(core)
            if core:
                parts.append(core)
        merged = " - ".join(parts)
    else:
        merged = scrub("".join(lines))

    # 去掉结尾的逗号 (全角/半角)
    merged = re.sub(r"[，,]+$", "", merged).strip()
    return merged


def flatten_en(text):
    """把英文原文合并成一行: 无论原来几行、是否对话, 都铺成一行。
    保留 HTML 标签; 对话中的 '- ' 说话人分隔改用 ' - ' 连接。"""
    lines = [ln.strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln]
    dash_lines = [ln for ln in lines if ln.startswith("-")]
    is_dialogue = len(dash_lines) >= 2
    if is_dialogue:
        parts = []
        for ln in lines:
            core = ln[1:].strip() if ln.startswith("-") else ln
            if core:
                parts.append(core)
        merged = " - ".join(parts)
    else:
        merged = " ".join(lines)
    return re.sub(r"[ \t]{2,}", " ", merged).strip()


# ----------------------------------------------------------------------------
# 术语表持久化
# ----------------------------------------------------------------------------
def load_glossary(path):
    seed = {
        "Uhtred": "乌特雷德", "Osbert": "奥斯伯特", "Ragnar": "拉格纳",
        "Ubba": "乌巴", "Kjartan": "基尔坦", "Ravn": "拉文",
        "Brida": "布丽达", "Thyra": "蒂拉", "Sven": "斯文",
        "Beocca": "贝奥卡", "Aelfric": "埃尔弗里克", "Ælfric": "埃尔弗里克",
        "Guthrum": "古思伦", "Storri": "斯托里", "Sigrid": "西格丽德",
        "Alfred": "阿尔弗雷德", "Aella": "埃拉", "Egbert": "埃格伯特",
        "Bebbanburg": "贝班堡", "Northumbria": "诺森布里亚",
        "Wessex": "威塞克斯", "Mercia": "麦西亚", "Eoferwic": "约克",
        "East Anglia": "东盎格利亚", "Cornwalum": "康沃卢姆",
        "Odin": "奥丁", "Thor": "托尔", "Woden": "沃登", "Valhalla": "英灵殿",
        "Danes": "丹麦人", "Saxons": "撒克逊人",
        "ealdorman": "郡长", "Ealdorman": "郡长", "Earl": "伯爵",
    }
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            seed.update(data)
        except Exception:
            pass
    return seed


def save_glossary(path, glossary):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(glossary, f, ensure_ascii=False, indent=2, sort_keys=True)


def format_glossary(glossary):
    return "\n".join(f"  {en} = {zh}" for en, zh in sorted(glossary.items()))


# ----------------------------------------------------------------------------
# LLM 调用
# ----------------------------------------------------------------------------
def make_client():
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        sys.exit("未设置 LLM_API_KEY 环境变量")
    base_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    return OpenAI(api_key=api_key, base_url=base_url)


def translate_batch(client, model, batch, glossary, max_retries=3):
    """batch: list[(id, en_text)] -> dict{id: zh_text}, 以及新术语。"""
    system = STYLE_RULES + GLOSSARY_INSTRUCTION.format(glossary=format_glossary(glossary))
    payload = [{"id": i, "en": t} for i, t in batch]
    user = json.dumps(payload, ensure_ascii=False)

    for attempt in range(1, max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.3,
            )
            raw = resp.choices[0].message.content.strip()
            # 去掉可能的 ```json ``` 包裹
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()
            data = json.loads(raw)
            result, new_terms = {}, {}
            for item in data:
                if item.get("id") == -1:
                    new_terms.update(item.get("new_terms", {}))
                else:
                    result[item["id"]] = item["zh"]
            return result, new_terms
        except Exception as e:
            print(f"    [重试 {attempt}/{max_retries}] {e}")
            time.sleep(2 * attempt)
    raise RuntimeError("该批次多次失败, 请检查网络/API 配置")


# ----------------------------------------------------------------------------
# 主翻译流程
# ----------------------------------------------------------------------------
def translate_file(path, client, model, glossary, glossary_path, batch_size=25):
    print(f"\n=== 翻译: {path} ===")
    cues = parse_srt(path)
    print(f"    共解析出 {len(cues)} 条字幕")

    # 收集需要翻译的条目 (跳过纯音效, 直接原样保留其结构)
    to_translate = []
    for idx, cue in enumerate(cues):
        if not is_pure_sound_cue(cue.text):
            to_translate.append((idx, cue.text))

    translations = {}  # cue_idx -> 中文
    for start in range(0, len(to_translate), batch_size):
        chunk = to_translate[start:start + batch_size]
        batch = [(idx, text) for idx, text in chunk]
        print(f"    翻译第 {start + 1}-{start + len(chunk)} / {len(to_translate)} 条...")
        result, new_terms = translate_batch(client, model, batch, glossary)
        for idx, _ in batch:
            translations[idx] = result.get(idx, "")
        if new_terms:
            print(f"    发现新术语: {new_terms}")
            glossary.update(new_terms)
            save_glossary(glossary_path, glossary)

    # 校验 + 补翻: 有实际台词却被模型漏返回(中文为空)的条目, 单独重翻
    missed = [(idx, text) for idx, text in to_translate
              if not translations.get(idx, "").strip() and has_translatable_text(text)]
    if missed:
        print(f"    检测到 {len(missed)} 条漏翻, 逐条补翻...")
        for start in range(0, len(missed), batch_size):
            chunk = missed[start:start + batch_size]
            result, new_terms = translate_batch(client, model, chunk, glossary)
            for idx, text in chunk:
                zh = result.get(idx, "").strip()
                translations[idx] = zh
                if not zh:
                    print(f"      警告: 行 {cues[idx].index} 仍未译出: {text!r}")
            if new_terms:
                glossary.update(new_terms)
                save_glossary(glossary_path, glossary)

    # 生成输出 (中上英下, 各自铺成一行)
    out_blocks = []
    for idx, cue in enumerate(cues):
        zh = clean_zh(translations.get(idx, ""))
        en = flatten_en(cue.text)
        if zh:
            body = zh + "\n" + en
        else:
            # 纯音效或无实际台词: 只保留英文原文
            body = en
        out_blocks.append(f"{cue.index}\n{cue.timecode}\n{body}")

    out_path = re.sub(r"\.srt$", "", path, flags=re.IGNORECASE) + ".zh-en.srt"
    with open(out_path, "w", encoding="utf-8-sig") as f:
        f.write("\n\n".join(out_blocks) + "\n")
    print(f"    已输出: {out_path}")
    return out_path


def main():
    ap = argparse.ArgumentParser(description="《孤国春秋》双语字幕翻译")
    ap.add_argument("target", help="单个 .srt 文件, 或配合 --batch 传目录")
    ap.add_argument("--batch", action="store_true", help="批量翻译目录下所有 .srt")
    ap.add_argument("--batch-size", type=int, default=25, help="每次请求翻译多少条 (默认25)")
    ap.add_argument("--glossary", default=None, help="术语表路径 (默认目标同目录 glossary.json)")
    args = ap.parse_args()

    model = os.environ.get("LLM_MODEL", "gpt-4o")
    client = make_client()

    if args.batch:
        base_dir = args.target
        srt_files = [
            os.path.join(base_dir, f) for f in os.listdir(base_dir)
            if f.lower().endswith(".srt") and not f.lower().endswith(".zh-en.srt")
        ]
    else:
        base_dir = os.path.dirname(os.path.abspath(args.target))
        srt_files = [args.target]

    glossary_path = args.glossary or os.path.join(base_dir, "glossary.json")
    glossary = load_glossary(glossary_path)
    save_glossary(glossary_path, glossary)  # 首次生成种子表

    for srt in sorted(srt_files):
        translate_file(srt, client, model, glossary, glossary_path, args.batch_size)

    print(f"\n全部完成。术语表: {glossary_path}")


if __name__ == "__main__":
    main()
