"""Synthetic H264 entirely in RAM; shared by tests and the offline benchmark."""
import base64
from fractions import Fraction
from io import BytesIO

import av
import numpy as np


def synthetic_video(*, seconds=7, width=128, height=96, fps=40):
    buffer = BytesIO()
    with av.open(buffer, 'w', format='mp4') as container:
        stream = container.add_stream('libx264', rate=fps)
        stream.width, stream.height, stream.pix_fmt = width, height, 'yuv420p'
        stream.codec_context.gop_size = fps
        stream.codec_context.max_b_frames = 0
        stream.options = {'preset': 'ultrafast', 'tune': 'zerolatency', 'crf': '28'}
        yy, xx = np.indices((height, width))
        base = np.stack((xx % 256, yy % 256, (xx+yy) % 256), axis=-1).astype(np.uint8)
        for index in range(int(seconds*fps)+1):
            image = np.roll(base, index*3, axis=1)
            frame = av.VideoFrame.from_ndarray(image, format='rgb24')
            frame.pts, frame.time_base = index, Fraction(1, fps)
            for packet in stream.encode(frame): container.mux(packet)
        for packet in stream.encode(): container.mux(packet)
    raw = buffer.getvalue()
    frames = []
    with av.open(BytesIO(raw)) as container:
        stream = container.streams.video[0]
        description = bytes(stream.codec_context.extradata)
        for packet in container.demux(stream):
            if packet.size:
                frames.append(dict(sequence=len(frames), timestampMs=float(packet.pts*packet.time_base*1000),
                                   keyframe=packet.is_keyframe, data=base64.b64encode(bytes(packet)).decode()))
    header = dict(version=1, generation='synthetic-1', codec='avc1.'+description[1:4].hex(),
                  description=base64.b64encode(description).decode(), width=width, height=height)
    return raw, header, frames


def batches(header, frames, size=4):
    from nivra.native_camera import video_packet
    for index in range(0, len(frames), size):
        value = {**header, 'frames': frames[index:index+size]}
        yield value, video_packet(value, 'synthetic', 'socket-1')[0]
