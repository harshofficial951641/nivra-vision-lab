"""Create local timestamped contact sheets; never infer or approve labels."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def read_samples(path, timestamps, size):
    capture = cv2.VideoCapture(str(path))
    frames = []
    try:
        if not capture.isOpened():
            raise ValueError(f'Cannot open {path.name}')
        for seconds in timestamps:
            if not capture.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000):
                raise ValueError(f'Cannot seek {path.name} to {seconds}')
            ok, frame = capture.read()
            if not ok:
                raise ValueError(f'Cannot decode {path.name} at {seconds}')
            frames.append((seconds, cv2.resize(frame, size)))
        return frames
    finally:
        capture.release()


def write_sheet(path, canvas):
    if not cv2.imwrite(str(path), canvas, [cv2.IMWRITE_JPEG_QUALITY, 90]):
        raise OSError(f'Contact sheet could not be written: {path}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--per-class', type=int, default=18)
    parser.add_argument('--dense', action='store_true', help='Also write 16 timestamped frames per selected recording')
    parser.add_argument('--archive', help='Review only one inventoried archive')
    args = parser.parse_args()
    root = args.data_root.resolve()
    if not 1 <= args.per_class <= 200:
        parser.error('--per-class must be between 1 and 200')
    inventory = json.loads((root / 'inventory.json').read_text())
    if args.archive:
        inventory = [row for row in inventory if row['archive'] == args.archive]
        if not inventory:
            parser.error('Selected archive is absent from inventory')
    cv2.setNumThreads(2)
    prefix = Path(args.archive).stem + '-' if args.archive else ''
    review = root / 'review'
    review.mkdir(exist_ok=True)
    selected = []
    for category in sorted({row['publisherCategory'] for row in inventory}):
        rows = sorted((row for row in inventory if row['publisherCategory'] == category
                       and row['durationSeconds'] >= 4), key=lambda row: row['sha256'])[:args.per_class]
        selected.extend(rows)
        if args.dense:
            for row in rows:
                path = (root / row['path']).resolve()
                if not path.is_relative_to(root):
                    raise ValueError('Video path escapes data root')
                canvas = np.full((4 * 178, 4 * 280, 3), 245, np.uint8)
                samples = read_samples(path, np.linspace(.1, row['durationSeconds'] - .1, 16), (280, 157))
                for index, (seconds, frame) in enumerate(samples):
                    top, left = (index // 4) * 178, (index % 4) * 280
                    canvas[top:top + 157, left:left + 280] = frame
                    cv2.putText(canvas, f'{row["id"]} {seconds:.2f}s', (left + 3, top + 174),
                                cv2.FONT_HERSHEY_SIMPLEX, .45, (15, 15, 15), 1, cv2.LINE_AA)
                write_sheet(review / f'{row["id"]}-dense.jpg', canvas)
        for page in range(0, len(rows), 6):
            canvas = np.full((6 * 160, 5 * 224, 3), 245, np.uint8)
            for index, row in enumerate(rows[page:page + 6]):
                path = (root / row['path']).resolve()
                if not path.is_relative_to(root):
                    raise ValueError('Video path escapes data root')
                samples = read_samples(path, np.linspace(.1, row['durationSeconds'] - .1, 5), (224, 126))
                for column, (seconds, frame) in enumerate(samples):
                    top, left = index * 160, column * 224
                    canvas[top:top + 126, left:left + 224] = frame
                    cv2.putText(canvas, f'{row["id"]} {seconds:.1f}s', (left + 3, top + 148),
                                cv2.FONT_HERSHEY_SIMPLEX, .42, (15, 15, 15), 1, cv2.LINE_AA)
            output = review / f'{prefix}{category}-{page // 6 + 1:02d}.jpg'
            write_sheet(output, canvas)
            print(output)
    (review / f'{prefix}selected.json').write_text(json.dumps(selected, indent=2) + '\n')


if __name__ == '__main__':
    main()
