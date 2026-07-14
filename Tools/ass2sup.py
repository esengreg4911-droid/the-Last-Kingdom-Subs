# -*- coding: utf-8 -*-
"""
ass2sup.py  --  Convert a styled .ass subtitle to Blu-ray PGS .sup
                with all visual effects preserved (fonts, colors,
                outline, positioning), via libass rendering.

Pipeline:
    ASS --(ass2bdnxml, libass)--> BDN XML + PNG --(SUPer)--> SUP

Usage:
    python ass2sup.py input.ass [output.sup]
    python ass2sup.py input.ass -v 1080p -f 23.976

If output is omitted, it is written next to the input as <name>.sup.
"""
import sys, os, argparse, subprocess, shutil, tempfile

# --- Tool locations (edit here if you move the tools) ---
ASS2BDNXML = r"D:\tools\ass2bdnxml\ass2bdnxml_v07g\ass2bdnxml.exe"
SUPER_CLI  = r"D:\tools\SUPer_cli\CLI_win_x64_SUPer\SUPer_CLI.exe"


def die(msg):
    print("ERROR:", msg, file=sys.stderr)
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="Convert styled ASS to Blu-ray PGS SUP (effects preserved).")
    ap.add_argument("input", help="Input .ass file")
    ap.add_argument("output", nargs="?", help="Output .sup file (default: alongside input)")
    ap.add_argument("-v", "--video-format", default="1080p",
                    help="Video format: 1080p,1080i,720p,576i,480i (def: 1080p)")
    ap.add_argument("-f", "--fps", default="23.976",
                    help="Frame rate: 23.976,24,25,29.97,50,59.94,60 (def: 23.976)")
    ap.add_argument("-b", "--bt", default="709", help="Rec. BT matrix: 601,709,2020 (def: 709)")
    ap.add_argument("-a", "--fontdir", default=None, help="Extra font directory for non-installed fonts")
    ap.add_argument("--keep-temp", action="store_true", help="Keep the intermediate BDN XML + PNG folder")
    args = ap.parse_args()

    ass_path = os.path.abspath(args.input)
    if not os.path.isfile(ass_path):
        die("input not found: " + ass_path)
    if not os.path.isfile(ASS2BDNXML):
        die("ass2bdnxml.exe not found at: " + ASS2BDNXML)
    if not os.path.isfile(SUPER_CLI):
        die("SUPer_CLI.exe not found at: " + SUPER_CLI)

    base = os.path.splitext(os.path.basename(ass_path))[0]
    out_path = os.path.abspath(args.output) if args.output \
        else os.path.join(os.path.dirname(ass_path), base + ".sup")

    # Intermediate work dir (BDN XML + PNGs). ass2bdnxml writes to CWD,
    # so we run it inside a dedicated temp folder.
    work = tempfile.mkdtemp(prefix="ass2sup_")
    try:
        # Step 1: ASS -> BDN XML + PNG  (libass render; -c names XML after input)
        cmd1 = [ASS2BDNXML, "-v", args.video_format, "-f", args.fps, "-c"]
        if args.fontdir:
            cmd1 += ["-a", args.fontdir]
        cmd1.append(ass_path)
        print(">> [1/2] rendering with libass ...")
        r = subprocess.run(cmd1, cwd=work)
        if r.returncode != 0:
            die("ass2bdnxml failed (exit %d)" % r.returncode)

        xmls = [f for f in os.listdir(work) if f.lower().endswith(".xml")]
        if not xmls:
            die("no BDN XML produced")
        xml_path = os.path.join(work, xmls[0])

        # Step 2: BDN XML -> SUP  (SUPer). No -q/-s upstream so SUPer handles it.
        cmd2 = [SUPER_CLI, "-i", xml_path, "-b", args.bt, "-y", out_path]
        print(">> [2/2] packing PGS with SUPer ...")
        r = subprocess.run(cmd2)
        if r.returncode != 0:
            die("SUPer failed (exit %d)" % r.returncode)

        if not os.path.isfile(out_path):
            die("SUP not created")
        size_kb = os.path.getsize(out_path) / 1024.0
        print(">> Done: %s  (%.1f KB)" % (out_path, size_kb))
    finally:
        if args.keep_temp:
            print(">> intermediate files kept at:", work)
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
