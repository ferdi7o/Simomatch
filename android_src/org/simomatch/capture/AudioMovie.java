package org.simomatch.capture;

import android.content.Context;
import android.media.*;
import android.net.Uri;
import android.os.SystemClock;
import android.util.Log;
import java.io.File;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

/** Lossless track remux, followed by actual AAC decode/non-silence verification. */
final class AudioMovie {
    private AudioMovie() { }

    static File combine(Context context, Uri video, PlaybackAudio audio, long videoOriginUs,
                        long videoEndUs) throws Exception {
        long offset = audio.originUs-videoOriginUs;
        Log.i("SimomatchAudio", "AUDIO_VIDEO_OFFSET_US="+offset);
        // Both clocks must be MONOTONIC; never silently accept a different codec clock.
        if (Math.abs(offset) > 2000000)
            throw new IllegalStateException("Audio/video clocks do not match: "+offset);
        File result = File.createTempFile("simomatch_av_", ".mp4", context.getCacheDir());
        MediaExtractor v = new MediaExtractor(), a = new MediaExtractor();
        MediaMuxer muxer = null;
        boolean started = false, success = false;
        try {
            v.setDataSource(context, video, null); a.setDataSource(audio.file.getAbsolutePath());
            int vi = track(v,"video/"), ai = track(a,"audio/");
            if (vi < 0 || ai < 0) throw new IllegalStateException("Missing AV track");
            v.selectTrack(vi); a.selectTrack(ai);
            muxer = new MediaMuxer(result.getAbsolutePath(), MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);
            int vt = muxer.addTrack(v.getTrackFormat(vi)), at = muxer.addTrack(a.getTrackFormat(ai));
            muxer.start(); started = true;
            // Interleave by presentation time, bounded memory; skip pre-video AAC
            // packets rather than shifting the whistle relative to the video.
            ByteBuffer buffer = ByteBuffer.allocateDirect(2*1024*1024);
            MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
            long lastVideo = -1, lastAudio = -1;
            int audioSamples = 0;
            while (true) {
                while (a.getSampleTime() >= 0 && a.getSampleTime()+offset < 0) a.advance();
                long vp = v.getSampleTime(), ap = a.getSampleTime();
                if (ap >= 0) ap += offset;
                if (ap > videoEndUs) ap = -1;
                if (vp < 0 && ap < 0) break;
                boolean videoNext = vp >= 0 && (ap < 0 || vp <= ap);
                MediaExtractor source = videoNext ? v : a;
                long pts = videoNext ? vp : ap;
                buffer.clear();
                int size = source.readSampleData(buffer,0);
                if (size < 0 || size > buffer.capacity()) throw new IllegalStateException("Invalid encoded sample size");
                int flags = (source.getSampleFlags() & MediaExtractor.SAMPLE_FLAG_SYNC) != 0
                        ? MediaCodec.BUFFER_FLAG_KEY_FRAME : 0;
                if (videoNext) { pts = Math.max(lastVideo+1,pts); lastVideo = pts; }
                else { pts = Math.max(lastAudio+1,pts); lastAudio = pts; audioSamples++; }
                info.set(0,size,pts,flags); buffer.position(0); buffer.limit(size);
                muxer.writeSampleData(videoNext ? vt : at,buffer,info);
                source.advance();
            }
            if (audioSamples == 0) throw new IllegalStateException("No synchronized AAC samples");
            muxer.stop(); started = false; muxer.release(); muxer = null;
            if (!hasAudibleAudio(result)) throw new IllegalStateException("Exported AAC decoded as silence/empty");
            success = true;
            return result;
        } finally {
            v.release(); a.release();
            try { if (started) muxer.stop(); } catch (Exception ignored) { }
            try { if (muxer != null) muxer.release(); } catch (Exception ignored) { }
            if (!success) result.delete();
        }
    }

    private static int track(MediaExtractor extractor, String prefix) {
        for (int i=0; i<extractor.getTrackCount(); i++) {
            String mime = extractor.getTrackFormat(i).getString(MediaFormat.KEY_MIME);
            if (mime != null && mime.startsWith(prefix)) return i;
        }
        return -1;
    }

    static boolean hasAudibleAudio(File movie) throws Exception {
        MediaExtractor extractor = new MediaExtractor();
        MediaCodec decoder = null;
        boolean started = false;
        long count = 0, audible = 0;
        double energy = 0;
        int peak = 0;
        try {
            extractor.setDataSource(movie.getAbsolutePath());
            int index = track(extractor,"audio/");
            if (index < 0) return false;
            extractor.selectTrack(index);
            MediaFormat format = extractor.getTrackFormat(index);
            format.setInteger(MediaFormat.KEY_PCM_ENCODING, AudioFormat.ENCODING_PCM_16BIT);
            decoder = MediaCodec.createDecoderByType(format.getString(MediaFormat.KEY_MIME));
            decoder.configure(format,null,null,0); decoder.start(); started = true;
            MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
            boolean inputEos = false, outputEos = false;
            long deadline = SystemClock.elapsedRealtime()+15000;
            while (!outputEos) {
                if (SystemClock.elapsedRealtime() > deadline) throw new IllegalStateException("AAC validation timeout");
                if (!inputEos) {
                    int input = decoder.dequeueInputBuffer(0);
                    if (input >= 0) {
                        ByteBuffer buffer = decoder.getInputBuffer(input);
                        if (buffer == null) throw new IllegalStateException("AAC decoder input missing");
                        buffer.clear(); int size = extractor.readSampleData(buffer,0);
                        inputEos = size < 0;
                        decoder.queueInputBuffer(input,0,inputEos ? 0 : size,
                                inputEos ? 0 : extractor.getSampleTime(),
                                inputEos ? MediaCodec.BUFFER_FLAG_END_OF_STREAM : 0);
                        if (!inputEos) extractor.advance();
                    }
                }
                int out = decoder.dequeueOutputBuffer(info,1000);
                if (out == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                    MediaFormat decoded = decoder.getOutputFormat();
                    if (decoded.containsKey(MediaFormat.KEY_PCM_ENCODING)
                            && decoded.getInteger(MediaFormat.KEY_PCM_ENCODING) != AudioFormat.ENCODING_PCM_16BIT)
                        throw new IllegalStateException("Unexpected decoded PCM encoding");
                } else if (out >= 0) {
                    ByteBuffer buffer = decoder.getOutputBuffer(out);
                    if (buffer != null && info.size > 0) {
                        buffer.position(info.offset); buffer.limit(info.offset+info.size);
                        buffer.order(ByteOrder.LITTLE_ENDIAN);
                        while (buffer.remaining() >= 2) {
                            int sample = buffer.getShort(), level = Math.abs(sample);
                            peak = Math.max(peak,level); count++; energy += (double)sample*sample;
                            if (level > 8) audible++;
                        }
                    }
                    outputEos = (info.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0;
                    decoder.releaseOutputBuffer(out,false);
                }
            }
            double rms = count == 0 ? 0 : Math.sqrt(energy/count);
            Log.i("SimomatchAudio", "AUDIO_MP4_VERIFIED samples="+count+" nonzero="+audible+" peak="+peak+" rms="+rms);
            return audible > 0 && rms > 1;
        } finally {
            try { if (started) decoder.stop(); } catch (Exception ignored) { }
            try { if (decoder != null) decoder.release(); } catch (Exception ignored) { }
            extractor.release();
        }
    }
}
