"""Inspect a pulled MP4 using ffprobe/ffmpeg, including decoded PCM non-silence.

python tools/check_recorded_audio.py match.mp4
Requires ffmpeg and ffprobe on PATH. Does not modify the movie. Track timestamps
and first audible time aid device listening tests; they do not prove AV sync.
"""
import argparse
from array import array
import json
import math
from pathlib import Path
import subprocess
import sys


def pcm_stats(chunks, rate=48000):
    samples = audible = peak = 0
    energy = 0
    first = None
    remainder = b''
    for chunk in chunks:
        data = remainder+chunk
        end = len(data)//2*2
        remainder = data[end:]
        values = array('h')
        values.frombytes(data[:end])
        if sys.byteorder != 'little':
            values.byteswap()
        for value in values:
            level = abs(value)
            if level > 8:
                if first is None:
                    first = samples/rate
                audible += 1
            peak = max(peak,level)
            energy += value*value
            samples += 1
    if remainder:
        raise ValueError('Truncated decoded PCM')
    rms = math.sqrt(energy/samples) if samples else 0.
    return dict(samples=samples, nonzero_samples=audible, peak=peak, rms=rms,
                rms_dbfs=20*math.log10(rms/32768) if rms else None,
                first_audible_second=first, decoded_seconds=samples/rate,
                audible=audible > 0 and rms > 1.)


def check(path):
    metadata = json.loads(subprocess.check_output(
        ['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],text=True))
    video = next((s for s in metadata['streams'] if s.get('codec_type') == 'video'),None)
    audio = next((s for s in metadata['streams'] if s.get('codec_type') == 'audio'),None)
    if not video or not audio or audio.get('codec_name') != 'aac':
        raise ValueError('Expected both video and AAC audio tracks')
    # Stream decoded data; never load an entire match's PCM into RAM.
    with subprocess.Popen(['ffmpeg','-v','error','-i',str(path),'-map','0:a:0',
                           '-ac','1','-ar','48000','-f','s16le','pipe:1'],
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
        stats = pcm_stats(iter(lambda:process.stdout.read(65536),b''))
        if process.wait() != 0:
            raise ValueError('AAC decode failed')
    report = dict(video_codec=video.get('codec_name'), audio_codec=audio['codec_name'],
                  video_start=video.get('start_time'), audio_start=audio.get('start_time'),
                  video_duration=video.get('duration'), audio_duration=audio.get('duration'), **stats)
    if not stats['audible']:
        raise ValueError('AAC track is empty/silent: '+json.dumps(report))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mp4',type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.mp4),ensure_ascii=False,indent=2))
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        parser.exit(1,str(error)+'\n')
