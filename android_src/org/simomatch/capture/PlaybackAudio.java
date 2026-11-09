package org.simomatch.capture;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.media.*;
import android.media.projection.MediaProjection;
import android.os.Process;
import android.util.Log;
import java.io.File;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/** Optional own-UID playback capture. Never creates a microphone audio source.
 * AAC is staged separately: an audio failure cannot poison the working video muxer.
 */
final class PlaybackAudio {
    private static final String TAG = "SimomatchAudio";
    private static final int RATE = 48000;
    private AudioRecord recorder;
    private MediaCodec encoder;
    private MediaMuxer muxer;
    private Thread thread;
    private volatile boolean stopping;
    private volatile boolean discardRequested;
    private volatile boolean startupFailed;
    private final CountDownLatch ready = new CountDownLatch(1);
    volatile boolean done, valid;
    volatile String error = "";
    volatile long originUs;
    private long frames, samples, audible;
    private int peak;
    private boolean muxing;
    final File file;

    PlaybackAudio(Context context, MediaProjection projection) throws Exception {
        file = File.createTempFile("simomatch_audio_", ".m4a", context.getCacheDir());
        try {
            if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED)
                throw new SecurityException("Oyun sesi izni verilmedi; video sessiz kaydedilecek.");
            AudioPlaybackCaptureConfiguration capture = new AudioPlaybackCaptureConfiguration.Builder(projection)
                    .addMatchingUid(Process.myUid())
                    .addMatchingUsage(AudioAttributes.USAGE_GAME)
                    .addMatchingUsage(AudioAttributes.USAGE_MEDIA)
                    .addMatchingUsage(AudioAttributes.USAGE_UNKNOWN).build();
            AudioFormat format = new AudioFormat.Builder().setSampleRate(RATE)
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setChannelMask(AudioFormat.CHANNEL_IN_MONO).build();
            int minimum = AudioRecord.getMinBufferSize(RATE, AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT);
            if (minimum <= 0) throw new IllegalStateException("Playback PCM format unavailable");
            recorder = new AudioRecord.Builder().setAudioFormat(format)
                    .setBufferSizeInBytes(Math.max(minimum * 4, 16384))
                    .setAudioPlaybackCaptureConfig(capture).build();
            if (recorder.getState() != AudioRecord.STATE_INITIALIZED)
                throw new IllegalStateException("Playback AudioRecord not initialized");
            encoder = MediaCodec.createEncoderByType("audio/mp4a-latm");
            MediaFormat aac = MediaFormat.createAudioFormat("audio/mp4a-latm", RATE, 1);
            aac.setInteger(MediaFormat.KEY_AAC_PROFILE, MediaCodecInfo.CodecProfileLevel.AACObjectLC);
            aac.setInteger(MediaFormat.KEY_BIT_RATE, 128000);
            aac.setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, 4096);
            encoder.configure(aac, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);
            muxer = new MediaMuxer(file.getAbsolutePath(), MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);
        } catch (Exception failure) { release(); file.delete(); throw failure; }
    }

    void start() {
        thread = new Thread(this::run, "SimomatchPlaybackAAC");
        thread.start();
        // Only the video encoder worker waits. Attach the display after capture
        // is ready, so the first-frame acknowledgement cannot precede audio.
        try {
            if (!ready.await(1500,TimeUnit.MILLISECONDS)) {
                startupFailed = true;
                error = "Oyun sesi başlangıcı zaman aşımına uğradı; sessiz video korundu.";
                stop();
            }
        } catch (InterruptedException failure) {
            startupFailed = true; stop(); Thread.currentThread().interrupt();
        }
    }

    private void run() {
        boolean codecStarted = false;
        try {
            encoder.start(); codecStarted = true;
            originUs = System.nanoTime()/1000;
            recorder.startRecording();
            if (recorder.getRecordingState() != AudioRecord.RECORDSTATE_RECORDING)
                throw new IllegalStateException("Playback capture did not start");
            ready.countDown();
            Log.i(TAG,"AUDIO_CAPTURE_STARTED own_uid="+Process.myUid()+" origin_us="+originUs);
            short[] pcm = new short[2048];
            MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
            AudioTimestamp timestamp = new AudioTimestamp();
            int track = -1;
            boolean inputEos = false, outputEos = false, timestampSet = false;
            long deadline = Long.MAX_VALUE;
            while (!outputEos) {
                if (stopping && deadline == Long.MAX_VALUE) deadline = android.os.SystemClock.elapsedRealtime()+2500;
                if (android.os.SystemClock.elapsedRealtime() > deadline)
                    throw new IllegalStateException("AAC EOS timeout");
                if (!inputEos) {
                    int input = encoder.dequeueInputBuffer(0);
                    if (input >= 0) {
                        ByteBuffer buffer = encoder.getInputBuffer(input);
                        if (buffer == null) throw new IllegalStateException("AAC input buffer missing");
                        buffer.clear(); buffer.order(ByteOrder.LITTLE_ENDIAN);
                        int count = stopping ? 0 : recorder.read(pcm, 0,
                                Math.min(pcm.length, buffer.remaining()/2), AudioRecord.READ_NON_BLOCKING);
                        if (count < 0) throw new IllegalStateException("Playback read error "+count);
                        if (!timestampSet && count > 0 && recorder.getTimestamp(timestamp,
                                AudioTimestamp.TIMEBASE_MONOTONIC) == AudioRecord.SUCCESS) {
                            originUs = timestamp.nanoTime/1000 - timestamp.framePosition*1000000/RATE;
                            timestampSet = true;
                        }
                        for (int i=0; i<count; i++) {
                            buffer.putShort(pcm[i]);
                            int level = Math.abs((int)pcm[i]);
                            peak = Math.max(peak, level); samples++;
                            if (level > 8) audible++;
                        }
                        encoder.queueInputBuffer(input, 0, count*2, frames*1000000/RATE,
                                stopping ? MediaCodec.BUFFER_FLAG_END_OF_STREAM : 0);
                        frames += count;
                        if (stopping) inputEos = true;
                    }
                }
                for (int n=0; n<8; n++) {
                    int out = encoder.dequeueOutputBuffer(info, 0);
                    if (out == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                        track = muxer.addTrack(encoder.getOutputFormat()); muxer.start(); muxing = true;
                    } else if (out >= 0) {
                        ByteBuffer buffer = encoder.getOutputBuffer(out);
                        if (info.size > 0 && muxing && buffer != null
                                && (info.flags & MediaCodec.BUFFER_FLAG_CODEC_CONFIG) == 0) {
                            buffer.position(info.offset); buffer.limit(info.offset+info.size);
                            muxer.writeSampleData(track, buffer, info);
                        }
                        outputEos = (info.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0;
                        encoder.releaseOutputBuffer(out, false);
                        if (outputEos) break;
                    } else break;
                }
                if (!outputEos) Thread.sleep(2);
            }
            valid = !startupFailed && muxing && samples > 0 && audible > 0;
            if (!valid && error.isEmpty()) error = "Oyun sesi örnekleri sessiz/boş; sessiz video korundu.";
        } catch (Exception failure) {
            error = failure.toString(); valid = false;
            Log.w(TAG, "AUDIO_CAPTURE_FAILED", failure);
        } finally {
            ready.countDown();
            try { if (codecStarted) encoder.stop(); } catch (Exception ignored) { }
            try { if (muxing) muxer.stop(); } catch (Exception failure) { valid = false; error = failure.toString(); }
            release();
            done = true;
            if (discardRequested) file.delete();
            Log.i(TAG, "AUDIO_PCM_SUMMARY samples="+samples+" nonzero="+audible+" peak="+peak+" valid="+valid);
        }
    }

    void stop() { stopping = true; }

    /** Called only on the encoder worker, never Kivy/Activity UI thread. */
    boolean await() {
        stop();
        try { if (thread != null) thread.join(3500); }
        catch (InterruptedException failure) { Thread.currentThread().interrupt(); }
        if (thread == null) { release(); done = true; }
        return done && valid;
    }

    void discard() {
        // If a vendor blocks despite NON_BLOCKING, the audio thread owns its
        // resources until exit; never release its codec from another thread.
        discardRequested = true;
        if (thread == null || done) file.delete();
    }

    private void release() {
        try {
            if (recorder != null && recorder.getRecordingState() == AudioRecord.RECORDSTATE_RECORDING)
                recorder.stop();
        } catch (Exception ignored) { }
        try { if (recorder != null) recorder.release(); } catch (Exception ignored) { }
        try { if (encoder != null) encoder.release(); } catch (Exception ignored) { }
        try { if (muxer != null) muxer.release(); } catch (Exception ignored) { }
    }
}
