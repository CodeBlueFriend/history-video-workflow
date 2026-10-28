"""Read-only rendered-motion check against source stills and a measured shot plan.

Estimates scale from exported pixels, not from animation code. Excludes title and
subtitle regions. A result is evidence for sampled frames, not full visual QA.
"""
import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('episode', type=Path)
    parser.add_argument('video', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    state = json.loads((args.episode / '00_项目记录/工作台状态.json').read_text())
    shots = state['plan']['shots']
    args.output.mkdir(parents=True, exist_ok=True)
    sheet = Image.new('RGB', (1440, len(shots) * 294), '#161616')
    draw = ImageDraw.Draw(sheet)
    rows = []
    for index, shot in enumerate(shots):
        source = Image.open(args.episode / state['assets'][shot['image']]['path']).convert('L')
        source = ImageOps.fit(source, (960, 540), method=Image.Resampling.BICUBIC)
        candidates = []
        upper = max(shot['start_crop']['scale'], shot['end_crop']['scale']) + .015
        scales = np.arange(1, upper, .001)
        for scale in scales:
            x = 480 * (1 - 1 / scale)
            y = 243 * (1 - 1 / scale)
            candidate = source.transform((960, 540), Image.Transform.AFFINE,
                                         (1 / scale, 0, x, 0, 1 / scale, y),
                                         resample=Image.Resampling.BICUBIC)
            candidates.append(np.asarray(candidate, dtype=float)[110:420, 110:850])
        start, end = shot['timeline_start_frame'], shot['timeline_end_exclusive']
        frames = [start + 15, (start + end - 1) // 2, end - 16]
        estimates = []
        for column, frame in enumerate(frames):
            raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-ss', str(frame / 30),
                                           '-i', str(args.video), '-frames:v', '1',
                                           '-vf', 'scale=960:540', '-pix_fmt', 'rgb24',
                                           '-f', 'rawvideo', '-'])
            actual = Image.frombytes('RGB', (960, 540), raw)
            target = np.asarray(actual.convert('L'), dtype=float)[110:420, 110:850]
            errors = [float(np.abs(candidate - target).mean()) for candidate in candidates]
            best = int(np.argmin(errors))
            estimate = float(scales[best])
            z0, z1 = shot['start_crop']['scale'], shot['end_crop']['scale']
            expected = z0 + (z1 - z0) * (frame - start) / (end - start - 1)
            estimates.append({'frame': frame, 'seconds': frame / 30,
                              'estimatedScale': round(estimate, 4),
                              'plannedScale': round(expected, 4),
                              'meanAbsolutePixelError': round(errors[best], 4)})
            sheet.paste(actual.resize((480, 270)), (column * 480, index * 294))
            draw.text((column * 480 + 8, index * 294 + 274),
                      f'{shot["id"]}  {frame / 30:.2f}s  scale~{estimate:.3f}', fill='white')
        increasing = shot['end_crop']['scale'] > shot['start_crop']['scale']
        values = [v['estimatedScale'] for v in estimates]
        monotonic = all((b > a if increasing else b < a) for a, b in zip(values, values[1:]))
        within = all(abs(v['estimatedScale'] - v['plannedScale']) <= .004 for v in estimates)
        rows.append({'shot': shot['id'], 'samples': estimates,
                     'sampledDirectionMatches': monotonic,
                     'sampledScaleMatchesWithin004': within})
    sheet.save(args.output / '镜头首中尾实测对照.jpg', quality=95)
    (args.output / '运动像素实测.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0 if all(r['sampledDirectionMatches'] and r['sampledScaleMatchesWithin004'] for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
