package org.simomatch.capture;

import android.app.*;
import android.content.*;
import android.content.pm.ServiceInfo;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.*;
import android.media.projection.*;
import android.net.Uri;
import android.os.*;
import android.provider.MediaStore;
import android.util.DisplayMetrics;
import android.view.Surface;
import org.json.JSONObject;
import java.nio.ByteBuffer;
import java.io.File;
import java.io.FileInputStream;
import java.io.OutputStream;

/** Single-use consent -> foreground service -> hardware AVC -> pending MediaStore MP4.
 * All codec, muxer and filesystem work runs on a HandlerThread, never the GL/UI thread.
 * Own-app playback audio is optional; microphone sources are never configured.
 */
public final class CaptureService extends Service {
    private static final Object LOCK = new Object();
    private static String current = "", state = "idle", message = "", output = "", cancelled = "";
    private static CaptureService instance;
    private static boolean verifiedAudio;
    private static final String CHANNEL = "simomatch_recording";
    private HandlerThread thread;
    private Handler worker;
    private String token = "";
    private MediaProjection projection;
    private MediaProjection.Callback projectionCallback;
    private VirtualDisplay display;
    private MediaCodec codec;
    private MediaMuxer muxer;
    private Surface surface;
    private ParcelFileDescriptor descriptor;
    private Uri uri;
    private Uri silentOriginal;
    private int track = -1, frames = 0, width, height, dpi;
    private boolean started, muxing, stopping, finished;
    private long firstPts = -1, lastPts = -1, stopDeadline;
    private String stopReason = "";
    private PlaybackAudio audio;
    private String audioFailure = "";
    private final MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();

    public static Intent consentIntent(Activity activity) {
        MediaProjectionManager manager = (MediaProjectionManager) activity.getSystemService(MEDIA_PROJECTION_SERVICE);
        // Stable full-display dimensions; never re-use an Intent returned by this API.
        if (Build.VERSION.SDK_INT >= 34)
            return manager.createScreenCaptureIntent(MediaProjectionConfig.createConfigForDefaultDisplay());
        return manager.createScreenCaptureIntent();
    }

    public static void prepare(Activity activity, String id, int result, Intent data, String name) {
        synchronized (LOCK) {
            if (instance != null || !(state.equals("idle") || state.equals("saved") ||
                    state.equals("failed") || state.equals("discarded")))
                throw new IllegalStateException("A previous recording is still closing");
            current = id; state = "preparing"; message = ""; output = ""; cancelled = "";
            verifiedAudio = false;
        }
        Intent intent = new Intent(activity, CaptureService.class);
        intent.putExtra("token", id).putExtra("result", result).putExtra("consent", data).putExtra("name", name);
        try {
            // Read display metrics from the visual Activity, not a Service context.
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Rect bounds = activity.getWindowManager().getMaximumWindowMetrics().getBounds();
                intent.putExtra("width", bounds.width()).putExtra("height", bounds.height());
            } else {
                DisplayMetrics metrics = new DisplayMetrics();
                activity.getWindowManager().getDefaultDisplay().getRealMetrics(metrics);
                intent.putExtra("width", metrics.widthPixels).putExtra("height", metrics.heightPixels);
            }
            intent.putExtra("dpi", activity.getResources().getConfiguration().densityDpi);
            activity.startForegroundService(intent);
        }
        catch (RuntimeException error) {
            publish(id, "failed", error.toString(), "");
            throw error;
        }
    }

    public static String status(String id) {
        synchronized (LOCK) {
            JSONObject json = new JSONObject();
            try {
                json.put("state", id.equals(current) ? state : "discarded");
                json.put("message", id.equals(current) ? message : "Kayıt oturumu artık geçerli değil.");
                json.put("uri", id.equals(current) ? output : "");
                json.put("audio_verified", id.equals(current) && verifiedAudio);
            } catch (Exception ignored) { }
            return json.toString();
        }
    }

    private static void publish(String id, String next, String detail, String path) {
        synchronized (LOCK) {
            if (!id.equals(current)) return;
            state = next; message = detail; output = path;
        }
    }

    public static void startRecording(String id) {
        synchronized (LOCK) {
            if (instance == null || !id.equals(instance.token) || !state.equals("prepared"))
                throw new IllegalStateException("Recorder is not prepared");
            CaptureService service = instance;
            service.worker.post(() -> service.begin());
        }
    }

    public static void stopRecording(String id) {
        synchronized (LOCK) {
            if (!id.equals(current)) return;
            cancelled = id;
            if (instance != null) {
                CaptureService service = instance;
                service.worker.post(() -> service.requestStop(""));
            }
        }
    }

    @Override public void onCreate() {
        super.onCreate();
        thread = new HandlerThread("SimomatchEncoder");
        thread.start(); worker = new Handler(thread.getLooper());
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null) { stopSelf(); return START_NOT_STICKY; }
        token = intent.getStringExtra("token");
        try {
            NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
            manager.createNotificationChannel(new NotificationChannel(CHANNEL, "Maç videosu", NotificationManager.IMPORTANCE_LOW));
            Intent launch = getPackageManager().getLaunchIntentForPackage(getPackageName());
            Notification notification = new Notification.Builder(this, CHANNEL)
                    .setSmallIcon(android.R.drawable.presence_video_online)
                    .setContentTitle("Simomatch maç kaydı")
                    .setContentText("Oyun videosu kaydı hazırlanıyor / sürüyor")
                    .setContentIntent(PendingIntent.getActivity(this, 0, launch,
                            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE))
                    .setOngoing(true).build();
            // Must happen before getMediaProjection(), after the user's consent.
            startForeground(4819, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION);
            synchronized (LOCK) { instance = this; }
            worker.post(() -> prepareEncoder(intent));
        } catch (Exception error) {
            publish(token, "failed", error.toString(), "");
            stopSelf();
        }
        return START_NOT_STICKY; // Never resurrect a consumed projection token.
    }

    private void prepareEncoder(Intent intent) {
        try {
            synchronized (LOCK) {
                if (token.equals(cancelled)) { finish(false, "Kayıt iptal edildi."); return; }
            }
            cleanupAbandonedPending();
            int screenWidth = intent.getIntExtra("width", 0), screenHeight = intent.getIntExtra("height", 0);
            dpi = intent.getIntExtra("dpi", 0);
            if (screenWidth <= 0 || dpi <= 0 || screenWidth >= screenHeight)
                throw new IllegalStateException("Video recording requires portrait display");
            String selected = chooseHardwareEncoder(screenWidth, screenHeight);
            if (selected == null) throw new IllegalStateException("No supported hardware H.264 portrait encoder");
            ContentValues values = new ContentValues();
            values.put(MediaStore.Video.Media.DISPLAY_NAME, intent.getStringExtra("name"));
            values.put(MediaStore.Video.Media.MIME_TYPE, "video/mp4");
            values.put(MediaStore.Video.Media.RELATIVE_PATH, "Movies/Simomatch/");
            values.put(MediaStore.Video.Media.IS_PENDING, 1);
            uri = getContentResolver().insert(MediaStore.Video.Media.EXTERNAL_CONTENT_URI, values);
            if (uri == null) throw new IllegalStateException("MediaStore insert failed");
            getSharedPreferences(CHANNEL, MODE_PRIVATE).edit().putString("pending", uri.toString()).commit();
            descriptor = getContentResolver().openFileDescriptor(uri, "rw");
            if (descriptor == null) throw new IllegalStateException("MediaStore file could not be opened");
            muxer = new MediaMuxer(descriptor.getFileDescriptor(), MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);
            codec = MediaCodec.createByCodecName(selected);
            MediaFormat format = MediaFormat.createVideoFormat("video/avc", width, height);
            format.setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface);
            format.setInteger(MediaFormat.KEY_BIT_RATE, 6_000_000);
            format.setInteger(MediaFormat.KEY_FRAME_RATE, 30);
            format.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1);
            format.setFloat(MediaFormat.KEY_MAX_FPS_TO_ENCODER, 30.f);
            // Keep a static final scoreboard in the movie for the full 3 seconds.
            format.setLong(MediaFormat.KEY_REPEAT_PREVIOUS_FRAME_AFTER, 33_333L);
            codec.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);
            surface = codec.createInputSurface();
            MediaProjectionManager manager = (MediaProjectionManager) getSystemService(MEDIA_PROJECTION_SERVICE);
            projection = manager.getMediaProjection(intent.getIntExtra("result", Activity.RESULT_CANCELED),
                    (Intent) intent.getParcelableExtra("consent"));
            if (projection == null) throw new IllegalStateException("MediaProjection rejected consent");
            projectionCallback = new MediaProjection.Callback() {
                @Override public void onStop() { requestStop("Android ekran kaydını durdurdu."); }
                @Override public void onCapturedContentResize(int w, int h) {
                    // Do not consume the token a second time or stretch a changed aspect ratio.
                    if (w > 0 && h > 0 && Math.abs((double) w/h - (double) width/height) > .025)
                        requestStop("Ekran oranı değişti; mevcut bölüm kaydedildi.");
                }
            };
            projection.registerCallback(projectionCallback, worker);
            // A single virtual display. Null surface excludes consent and countdown.
            display = projection.createVirtualDisplay("Simomatch", width, height, dpi,
                    DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR, null, null, worker);
            if (display == null) throw new IllegalStateException("Virtual display allocation failed");
            // Optional only. No AudioSource.MIC or microphone foreground service.
            try {
                ((AudioManager)getSystemService(AUDIO_SERVICE)).setAllowedCapturePolicy(AudioAttributes.ALLOW_CAPTURE_BY_ALL);
                audio = new PlaybackAudio(this, projection);
            } catch (Exception error) {
                audioFailure = error.toString();
                android.util.Log.w("SimomatchAudio", "AUDIO_PREPARE_FALLBACK_SILENT", error);
            }
            synchronized (LOCK) {
                if (token.equals(cancelled)) { finish(false, "Kayıt iptal edildi."); return; }
            }
            publish(token, "prepared", "", "");
        } catch (Exception error) { finish(false, error.toString()); }
    }

    private String chooseHardwareEncoder(int screenWidth, int screenHeight) {
        double maxScale = Math.min(1., Math.min(1080. / screenWidth, 1920. / screenHeight));
        for (double factor : new double[] {1., .75, .5}) {
            for (MediaCodecInfo item : new MediaCodecList(MediaCodecList.REGULAR_CODECS).getCodecInfos()) {
                if (!item.isEncoder() || !item.isHardwareAccelerated()) continue;
                try {
                    MediaCodecInfo.CodecCapabilities caps = item.getCapabilitiesForType("video/avc");
                    boolean inputSurface = false;
                    for (int color : caps.colorFormats)
                        if (color == MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface) inputSurface = true;
                    if (!inputSurface) continue;
                    MediaCodecInfo.VideoCapabilities video = caps.getVideoCapabilities();
                    int wa = Math.max(2, video.getWidthAlignment()), ha = Math.max(2, video.getHeightAlignment());
                    int w = (int) (screenWidth*maxScale*factor)/wa*wa;
                    int h = (int) (screenHeight*maxScale*factor)/ha*ha;
                    if (w > 0 && h > 0 && video.areSizeAndRateSupported(w, h, 30)
                            && video.getBitrateRange().contains(6_000_000)) {
                        width = w; height = h; return item.getName();
                    }
                } catch (IllegalArgumentException ignored) { }
            }
        }
        return null;
    }

    private void begin() {
        if (finished || stopping || started) return;
        try {
            publish(token, "starting", "", "");
            codec.start(); started = true;
            if (audio != null) audio.start();
            display.setSurface(surface);
            worker.post(this::drain);
        } catch (Exception error) { finish(false, error.toString()); }
    }

    private void drain() {
        if (finished || !started) return;
        try {
            // Bounded work per iteration. No encoder busy-wait on the UI thread.
            for (int n = 0; n < 8; n++) {
                int index = codec.dequeueOutputBuffer(info, 0);
                if (index == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                    if (muxing) throw new IllegalStateException("Encoder format changed twice");
                    track = muxer.addTrack(codec.getOutputFormat()); muxer.start(); muxing = true;
                } else if (index >= 0) {
                    ByteBuffer buffer = codec.getOutputBuffer(index);
                    boolean eos = (info.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0;
                    if ((info.flags & MediaCodec.BUFFER_FLAG_CODEC_CONFIG) != 0) info.size = 0;
                    if (info.size > 0 && muxing && buffer != null) {
                        if (firstPts < 0) firstPts = info.presentationTimeUs;
                        info.presentationTimeUs = Math.max(lastPts+1, info.presentationTimeUs-firstPts);
                        lastPts = info.presentationTimeUs;
                        buffer.position(info.offset); buffer.limit(info.offset+info.size);
                        muxer.writeSampleData(track, buffer, info);
                        frames++;
                        if (frames == 1 && !stopping) publish(token, "recording", "", "");
                    }
                    codec.releaseOutputBuffer(index, false);
                    if (eos) { finish(true, stopReason); return; }
                } else break;
            }
            if (stopping && SystemClock.elapsedRealtime() >= stopDeadline) {
                finish(true, stopReason.isEmpty() ? "Encoder kapanışı zaman aşımına uğradı; kısmi kayıt." : stopReason);
                return;
            }
            worker.postDelayed(this::drain, 8);
        } catch (Exception error) { finish(true, "Kayıt kesildi: "+error); }
    }

    private void requestStop(String reason) {
        if (finished || stopping) return;
        stopReason = reason;
        if (!started) { finish(false, reason.isEmpty() ? "Kayıt başlamadan iptal edildi." : reason); return; }
        stopping = true;
        if (audio != null) audio.stop();
        publish(token, "stopping", reason, "");
        try {
            if (display != null) display.setSurface(null);
            codec.signalEndOfInputStream();
            stopDeadline = SystemClock.elapsedRealtime()+3000;
        } catch (Exception error) { finish(true, "Kayıt kesildi: "+error); }
    }

    private void finish(boolean keepPartial, String detail) {
        if (finished) return;
        finished = true;
        worker.removeCallbacksAndMessages(null);
        boolean valid = keepPartial && muxing && frames > 1 && lastPts > 0;
        boolean audioReady = audio != null && audio.await();
        try { if (display != null) display.release(); } catch (Exception ignored) { }
        try { if (codec != null && started) codec.stop(); } catch (Exception ignored) { }
        try { if (codec != null) codec.release(); } catch (Exception ignored) { }
        try { if (surface != null) surface.release(); } catch (Exception ignored) { }
        try { if (muxing) muxer.stop(); } catch (Exception error) { valid = false; }
        try { if (muxer != null) muxer.release(); } catch (Exception ignored) { }
        try { if (descriptor != null) descriptor.close(); } catch (Exception error) { valid = false; }
        try {
            if (projection != null) {
                if (projectionCallback != null) projection.unregisterCallback(projectionCallback);
                projection.stop();
            }
        } catch (Exception ignored) { }
        if (valid) valid = validateMovie();
        if (valid && audioReady) {
            try {
                attachAudio();
                synchronized (LOCK) { if (token.equals(current)) verifiedAudio = true; }
            } catch (Exception error) {
                audioFailure = error.toString();
                android.util.Log.w("SimomatchAudio", "AUDIO_REMUX_FALLBACK_SILENT", error);
            }
        } else if (audio != null) {
            audioFailure = audio.error.isEmpty() ? "Oyun sesi yakalanamadı / AAC zaman aşımı." : audio.error;
        }
        if (audio != null) audio.discard();
        if (!audioFailure.isEmpty()) detail += (detail.isEmpty() ? "" : " ")+audioFailure;
        boolean saved = false;
        try {
            if (uri != null && valid) {
                ContentValues values = new ContentValues(); values.put(MediaStore.Video.Media.IS_PENDING, 0);
                saved = getContentResolver().update(uri, values, null, null) == 1;
            }
        } catch (Exception error) { detail = error.toString(); }
        if (!saved && silentOriginal != null) {
            // A candidate publication error must not delete the known-good
            // silent movie (e.g. storage/provider failure while adding audio).
            Uri failedCandidate = uri;
            uri = silentOriginal; silentOriginal = null;
            synchronized (LOCK) { if (token.equals(current)) verifiedAudio = false; }
            try {
                ContentValues values = new ContentValues(); values.put(MediaStore.Video.Media.IS_PENDING,0);
                saved = getContentResolver().update(uri,values,null,null) == 1;
            } catch (Exception error) { detail += " "+error; }
            try { getContentResolver().delete(failedCandidate,null,null); } catch (Exception ignored) { }
        }
        if (saved && silentOriginal != null) {
            try { getContentResolver().delete(silentOriginal,null,null); } catch (Exception ignored) { }
        }
        if (!saved && uri != null) {
            try { getContentResolver().delete(uri, null, null); } catch (Exception ignored) { }
        }
        getSharedPreferences(CHANNEL, MODE_PRIVATE).edit().remove("pending").remove("pending_audio").commit();
        publish(token, saved ? "saved" : (started ? "failed" : "discarded"), detail, saved ? uri.toString() : "");
        stopForeground(STOP_FOREGROUND_REMOVE);
        stopSelf();
        thread.quitSafely();
    }

    /** Never overwrite the known-good silent MP4. Publish a verified replacement
     * only after remux and copy complete; any audio/disk error retains the original.
     */
    private void attachAudio() throws Exception {
        File combined = AudioMovie.combine(this, uri, audio, firstPts, lastPts);
        Uri replacement = null;
        boolean committed = false;
        try {
            String name;
            try (android.database.Cursor cursor = getContentResolver().query(uri,
                    new String[]{MediaStore.Video.Media.DISPLAY_NAME},null,null,null)) {
                if (cursor == null || !cursor.moveToFirst()) throw new IllegalStateException("Video name missing");
                name = cursor.getString(0);
            }
            ContentValues values = new ContentValues();
            values.put(MediaStore.Video.Media.DISPLAY_NAME,name);
            values.put(MediaStore.Video.Media.MIME_TYPE,"video/mp4");
            values.put(MediaStore.Video.Media.RELATIVE_PATH,"Movies/Simomatch/");
            values.put(MediaStore.Video.Media.IS_PENDING,1);
            replacement = getContentResolver().insert(MediaStore.Video.Media.EXTERNAL_CONTENT_URI,values);
            if (replacement == null) throw new IllegalStateException("Audio video MediaStore insert failed");
            // Persist the candidate separately so process death can clean both rows.
            getSharedPreferences(CHANNEL,MODE_PRIVATE).edit().putString("pending_audio",replacement.toString()).commit();
            try (FileInputStream input = new FileInputStream(combined);
                 OutputStream out = getContentResolver().openOutputStream(replacement,"w")) {
                if (out == null) throw new IllegalStateException("Audio video output missing");
                byte[] bytes = new byte[65536]; int count;
                while ((count=input.read(bytes)) >= 0) out.write(bytes,0,count);
                out.flush();
            }
            // The source MP4 has been decoded/verified; ensure the copied file is whole.
            try (ParcelFileDescriptor fd = getContentResolver().openFileDescriptor(replacement,"r")) {
                if (fd == null || fd.getStatSize() != combined.length())
                    throw new IllegalStateException("Incomplete audio video copy");
            }
            // Keep candidate pending until the normal finalization below.
            silentOriginal = uri;
            uri = replacement; committed = true;
        } finally {
            combined.delete();
            if (!committed && replacement != null) {
                try { getContentResolver().delete(replacement,null,null); } catch (Exception ignored) { }
            }
            if (!committed) getSharedPreferences(CHANNEL,MODE_PRIVATE).edit().remove("pending_audio").commit();
        }
    }

    private boolean validateMovie() {
        MediaMetadataRetriever retriever = new MediaMetadataRetriever();
        try {
            retriever.setDataSource(this, uri);
            String duration = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION);
            boolean valid = "yes".equals(retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_HAS_VIDEO))
                    && duration != null && Long.parseLong(duration) > 0;
            if (!valid) return false;
            android.graphics.Bitmap frame = retriever.getScaledFrameAtTime(0,
                    MediaMetadataRetriever.OPTION_CLOSEST_SYNC, 160, 160);
            if (frame == null) return false;
            frame.recycle();
            return true;
        } catch (Exception error) { return false; }
        finally { try { retriever.release(); } catch (Exception ignored) { } }
    }

    private void cleanupAbandonedPending() {
        cleanupPendingKey("pending");
        cleanupPendingKey("pending_audio");
    }

    private void cleanupPendingKey(String key) {
        String old = getSharedPreferences(CHANNEL, MODE_PRIVATE).getString(key, "");
        if (old.isEmpty()) return;
        // Only a URI previously created by this service, and still IS_PENDING.
        Uri previous = Uri.parse(old);
        try (android.database.Cursor cursor = getContentResolver().query(previous,
                new String[] {MediaStore.Video.Media.IS_PENDING}, null, null, null)) {
            if (cursor != null && cursor.moveToFirst() && cursor.getInt(0) == 1)
                getContentResolver().delete(previous, null, null);
        } catch (Exception ignored) { }
    }

    @Override public void onTaskRemoved(Intent rootIntent) { worker.post(() -> requestStop("Uygulama kapatıldı; kısmi kayıt.")); }
    @Override public void onDestroy() {
        synchronized (LOCK) { if (instance == this) instance = null; }
        if (!finished) worker.post(() -> finish(true, "Kayıt servisi kapatıldı; kısmi kayıt."));
        super.onDestroy();
    }
    @Override public IBinder onBind(Intent intent) { return null; }
}
