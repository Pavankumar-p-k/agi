// android/app/src/main/java/com/jarvis/app/JarvisWakeService.java
//
// This is the Android Foreground Service that:
//  1. Shows a persistent notification (keeps the process alive)
//  2. Runs a Porcupine wake word engine in a background thread
//  3. When "Hey Jarvis" is detected, wakes the screen and
//     sends a broadcast Flutter can hear
//  4. Survives screen-off, Doze mode, and app switching

package com.example.jarvis_app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;
import android.util.Log;

import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.Arrays;

public class JarvisWakeService extends Service {

    private static final String TAG              = "JarvisWakeService";
    private static final String CHANNEL_ID       = "jarvis_wake_channel";
    private static final int    NOTIFICATION_ID  = 1001;
    public  static final String ACTION_WAKE      = "com.example.jarvis_app.WAKE_DETECTED";
    public  static final String ACTION_START     = "com.example.jarvis_app.START_WAKE";
    public  static final String ACTION_STOP      = "com.example.jarvis_app.STOP_WAKE";

    // Audio settings matching Porcupine requirements
    private static final int SAMPLE_RATE    = 16000;
    private static final int FRAME_LENGTH   = 512;   // Porcupine frame size
    private static final int CHANNEL_CONFIG = AudioFormat.CHANNEL_IN_MONO;
    private static final int AUDIO_FORMAT   = AudioFormat.ENCODING_PCM_16BIT;

    private Thread          _listenThread;
    private volatile boolean _running = false;
    private AudioRecord     _audioRecord;
    private PowerManager.WakeLock _wakeLock;

    // ── Simple keyword detector (no Porcupine license needed) ──
    // Uses energy + pattern detection as fallback
    // For production: replace _detectKeyword() with Porcupine SDK
    private SimpleKeywordDetector _detector;

    @Override
    public void onCreate() {
        super.onCreate();
        Log.d(TAG, "JarvisWakeService created");
        createNotificationChannel();
        _detector = new SimpleKeywordDetector();

        // Acquire partial wake lock so CPU stays on for audio processing
        PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
        _wakeLock = pm.newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK,
            "JarvisWakeService::WakeLock"
        );
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            stopSelf();
            return START_NOT_STICKY;
        }

        try {
            // Start as foreground with persistent notification
            startForeground(NOTIFICATION_ID, buildNotification("Listening for wake word..."));

            if (!_running) {
                startListening();
            }

            // START_STICKY = Android will restart this service if it's killed
            return START_STICKY;
        } catch (SecurityException e) {
            Log.e(TAG, "Wake service cannot start (missing permissions): " + e.getMessage());
            stopSelf();
            return START_NOT_STICKY;
        } catch (Exception e) {
            Log.e(TAG, "Wake service failed to start", e);
            stopSelf();
            return START_NOT_STICKY;
        }
    }

    @Override
    public void onDestroy() {
        Log.d(TAG, "JarvisWakeService stopping");
        stopListening();
        if (_wakeLock != null && _wakeLock.isHeld()) {
            _wakeLock.release();
        }
        super.onDestroy();
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) { return null; }


    // ════════════════════════════════════════
    //  AUDIO LISTENING LOOP
    // ════════════════════════════════════════

    private void startListening() {
        _running = true;
        if (!_wakeLock.isHeld()) _wakeLock.acquire();

        _listenThread = new Thread(() -> {
            android.os.Process.setThreadPriority(
                android.os.Process.THREAD_PRIORITY_AUDIO
            );

            int bufferSize = Math.max(
                AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL_CONFIG, AUDIO_FORMAT),
                FRAME_LENGTH * 2 * 2  // 2 frames, 2 bytes per sample
            );

            _audioRecord = new AudioRecord(
                MediaRecorder.AudioSource.VOICE_RECOGNITION,
                SAMPLE_RATE,
                CHANNEL_CONFIG,
                AUDIO_FORMAT,
                bufferSize
            );

            if (_audioRecord.getState() != AudioRecord.STATE_INITIALIZED) {
                Log.e(TAG, "AudioRecord failed to initialize");
                _running = false;
                return;
            }

            _audioRecord.startRecording();
            Log.d(TAG, "Wake word listening started");

            short[] frameBuffer = new short[FRAME_LENGTH];

            while (_running) {
                int samplesRead = _audioRecord.read(frameBuffer, 0, FRAME_LENGTH);

                if (samplesRead == FRAME_LENGTH) {
                    // Check for wake word
                    if (_detector.process(frameBuffer)) {
                        Log.d(TAG, "WAKE WORD DETECTED!");
                        onWakeWordDetected();
                    }
                }
            }

            _audioRecord.stop();
            _audioRecord.release();
            Log.d(TAG, "Wake word listening stopped");

        }, "JarvisWakeThread");

        _listenThread.setDaemon(true);
        _listenThread.start();
    }

    private void stopListening() {
        _running = false;
        if (_listenThread != null) {
            _listenThread.interrupt();
            _listenThread = null;
        }
        if (_wakeLock != null && _wakeLock.isHeld()) {
            _wakeLock.release();
        }
    }


    // ════════════════════════════════════════
    //  WAKE WORD DETECTED
    // ════════════════════════════════════════

    private void onWakeWordDetected() {
        // 1. Wake the screen
        wakeScreen();

        // 2. Update notification
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        nm.notify(NOTIFICATION_ID, buildNotification("Wake word detected!"));

        // 3. Send broadcast to Flutter (MethodChannel picks this up)
        Intent broadcast = new Intent(ACTION_WAKE);
        broadcast.setPackage(getPackageName());
        sendBroadcast(broadcast);

        // Reset notification after 2 seconds
        new android.os.Handler(android.os.Looper.getMainLooper())
            .postDelayed(() -> {
                NotificationManager nm2 = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
                nm2.notify(NOTIFICATION_ID, buildNotification("Listening for wake word..."));
            }, 2000);
    }

    private void wakeScreen() {
        PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
        PowerManager.WakeLock screenLock = pm.newWakeLock(
            PowerManager.SCREEN_BRIGHT_WAKE_LOCK
                | PowerManager.ACQUIRE_CAUSES_WAKEUP
                | PowerManager.ON_AFTER_RELEASE,
            "JarvisWakeService::ScreenWake"
        );
        screenLock.acquire(3000); // Hold for 3 seconds to allow app to open
        screenLock.release();
    }


    // ════════════════════════════════════════
    //  NOTIFICATION
    // ════════════════════════════════════════

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                "JARVIS Wake Service",
                NotificationManager.IMPORTANCE_LOW   // Low = silent, no vibration
            );
            channel.setDescription("Listens for 'Hey Jarvis' in the background");
            channel.setShowBadge(false);
            channel.setSound(null, null);
            channel.enableLights(false);
            channel.enableVibration(false);

            NotificationManager nm = getSystemService(NotificationManager.class);
            nm.createNotificationChannel(channel);
        }
    }

    private Notification buildNotification(String status) {
        Intent openApp = new Intent(this, MainActivity.class);
        openApp.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pendingIntent = PendingIntent.getActivity(
            this, 0, openApp,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        // Stop action
        Intent stopIntent = new Intent(this, JarvisWakeService.class);
        stopIntent.setAction(ACTION_STOP);
        PendingIntent stopPending = PendingIntent.getService(
            this, 1, stopIntent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        return new NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("J.A.R.V.I.S")
            .setContentText(status)
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentIntent(pendingIntent)
            .setOngoing(true)           // Cannot be dismissed by user
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setSilent(true)
            .addAction(android.R.drawable.ic_delete, "Stop", stopPending)
            .build();
    }


    // ════════════════════════════════════════
    //  SIMPLE KEYWORD DETECTOR
    //  (Energy-based, no SDK needed)
    //  Replace with Porcupine for production
    // ════════════════════════════════════════

    private static class SimpleKeywordDetector {
        // Rolling energy window
        private final double[] _energyHistory = new double[30];
        private int _historyIdx = 0;
        private int _triggerCount = 0;
        private long _lastTriggerMs = 0;

        // NOTE: For real wake word detection, replace this class with:
        // Porcupine (free tier available): https://picovoice.ai/platform/porcupine/
        // OR use Vosk keyword spotting (open source):
        //   vosk.SetWords(true); check for "jarvis" in results

        boolean process(short[] frame) {
            // Calculate frame energy (RMS)
            double energy = 0;
            for (short s : frame) energy += (double) s * s;
            energy = Math.sqrt(energy / frame.length);

            _energyHistory[_historyIdx % _energyHistory.length] = energy;
            _historyIdx++;

            // Simple voice activity detection:
            // If we get sustained energy above threshold → treat as voice
            // This is just a placeholder for demo — use Porcupine for real wake word
            double avgEnergy = 0;
            for (double e : _energyHistory) avgEnergy += e;
            avgEnergy /= _energyHistory.length;

            boolean isVoice = energy > 800 && energy > avgEnergy * 3;

            if (isVoice) {
                _triggerCount++;
                if (_triggerCount >= 8) {  // ~250ms of voice
                    long now = System.currentTimeMillis();
                    if (now - _lastTriggerMs > 3000) {  // cooldown 3s
                        _lastTriggerMs = now;
                        _triggerCount = 0;
                        return true;
                    }
                }
            } else {
                _triggerCount = Math.max(0, _triggerCount - 1);
            }
            return false;
        }
    }
}
