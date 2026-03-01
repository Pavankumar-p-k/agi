package com.example.jarvis_app.call;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.media.AudioManager;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import android.telecom.TelecomManager;
import android.telephony.TelephonyManager;
import android.util.Log;

import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;
import androidx.core.content.ContextCompat;

import com.example.jarvis_app.storage.CallLogDb;
import com.example.jarvis_app.storage.CallRecord;
import com.example.jarvis_app.sync.WindowsSync;
import com.example.jarvis_app.vosk.VoskEngine;
import com.example.jarvis_app.wishes.WishEngine;

public class CallAssistantService extends Service {
    private static final String TAG = "JarvisCallService";
    private static final String CHANNEL_ID = "jarvis_call_channel";
    private static final int NOTIFICATION_ID = 2001;
    private static final int LISTEN_DURATION_MS = 30000;

    public static final String ACTION_STOP = "com.jarvis.app.STOP_CALL_SERVICE";
    public static final String ACTION_VOIP_ANSWERED = "com.jarvis.app.VOIP_ANSWERED";
    public static final String ACTION_NEW_RECORD = "com.jarvis.app.NEW_CALL_RECORD";

    private static final String PREF_VOICE_GENDER = "call_voice_gender";

    private PowerManager.WakeLock wakeLock;
    private AudioManager audioManager;
    private JarvisTts tts;
    private VoskEngine voskEngine;
    private CallLogDb callLogDb;
    private WindowsSync windowsSync;
    private WishEngine wishEngine;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private volatile boolean recording = false;
    private volatile boolean callInProgress = false;
    private volatile int activeSessionId = 0;
    private volatile String currentCaller = "Unknown";
    private volatile String currentPlatform = "SIM";

    private final BroadcastReceiver callReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            String state = intent.getStringExtra(TelephonyManager.EXTRA_STATE);
            String number = intent.getStringExtra(TelephonyManager.EXTRA_INCOMING_NUMBER);
            if (number != null && !number.trim().isEmpty()) {
                currentCaller = number;
            }

            if (TelephonyManager.EXTRA_STATE_RINGING.equals(state)) {
                int sessionId = beginNewSession("SIM", currentCaller);
                long delay = getPrefs().getLong("call_answer_delay_ms", 4000L);
                handler.postDelayed(() -> autoAnswerSimCall(sessionId), delay);
            } else if (TelephonyManager.EXTRA_STATE_IDLE.equals(state)) {
                onCallEnded();
            }
        }
    };

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();

        audioManager = (AudioManager) getSystemService(AUDIO_SERVICE);
        tts = new JarvisTts(this);
        voskEngine = new VoskEngine(this);
        callLogDb = new CallLogDb(this);
        windowsSync = new WindowsSync();
        wishEngine = new WishEngine();

        SharedPreferences prefs = getPrefs();
        prefs.edit().putString(PREF_VOICE_GENDER, "male").apply();
        windowsSync.setPcIp(prefs.getString("call_pc_ip", "192.168.1.100"));

        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "Jarvis:CallAssistant");

        IntentFilter filter = new IntentFilter("android.intent.action.PHONE_STATE");
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(callReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(callReceiver, filter);
        }
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null) {
            String action = intent.getAction();
            if (ACTION_STOP.equals(action)) {
                clearActiveSession(true);
                stopSelf();
                return START_NOT_STICKY;
            }
            if (ACTION_VOIP_ANSWERED.equals(action)) {
                String platform = intent.getStringExtra("platform") == null ? "VOIP" : intent.getStringExtra("platform");
                String caller = intent.getStringExtra("caller_name") == null ? "Unknown" : intent.getStringExtra("caller_name");
                int sessionId = beginNewSession(platform, caller);
                handler.postDelayed(() -> enableSpeakerPhone(sessionId), 500);
                handler.postDelayed(() -> speakGreetingAndListen(sessionId), 1200);
            }
        }

        startForeground(NOTIFICATION_ID, buildNotification("Monitoring incoming calls"));
        if (!wakeLock.isHeld()) {
            wakeLock.acquire();
        }
        return START_STICKY;
    }

    @SuppressLint("MissingPermission")
    private void autoAnswerSimCall(int sessionId) {
        if (!isSessionActive(sessionId)) return;
        if (!hasPermission(Manifest.permission.ANSWER_PHONE_CALLS)) return;
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                TelecomManager telecomManager = (TelecomManager) getSystemService(TELECOM_SERVICE);
                telecomManager.acceptRingingCall();
            }
            updateNotification("Call answered, greeting caller");
            handler.postDelayed(() -> enableSpeakerPhone(sessionId), 600);
            handler.postDelayed(() -> speakGreetingAndListen(sessionId), 1200);
        } catch (Exception ex) {
            Log.e(TAG, "Auto-answer failed: " + ex.getMessage());
        }
    }

    private void enableSpeakerPhone(int sessionId) {
        if (!isSessionActive(sessionId)) return;
        try {
            audioManager.setMode(AudioManager.MODE_IN_COMMUNICATION);
            audioManager.setMicrophoneMute(false);
            audioManager.setSpeakerphoneOn(true);
        } catch (Exception ignored) {
        }
    }

    private void speakGreetingAndListen(int sessionId) {
        if (!isSessionActive(sessionId)) return;
        String wish = wishEngine.getWish(currentCaller);
        String fallback = getPrefs().getString(
            "call_custom_message",
            "Pavan is currently busy and cannot take your call. Please leave a note after the beep."
        );
        String greeting = wish + " " + fallback + " Beep.";
        tts.refreshVoicePreference();
        tts.speak(greeting, () -> startListening(sessionId));
    }

    private void startListening(int sessionId) {
        if (!isSessionActive(sessionId) || recording) return;
        recording = true;
        updateNotification("Listening for caller message");
        voskEngine.startListening(new VoskEngine.ResultCallback() {
            @Override
            public void onPartialResult(String text) {
                // No-op.
            }

            @Override
            public void onFinalResult(String transcript, String audioPath) {
                recording = false;
                processTranscript(sessionId, transcript, audioPath);
            }

            @Override
            public void onError(String error) {
                recording = false;
                processTranscript(sessionId, "", "");
            }
        });

        handler.postDelayed(() -> {
            if (!isSessionActive(sessionId) || !recording) return;
            voskEngine.stopListening();
            recording = false;
            processTranscript(sessionId, "", "");
        }, LISTEN_DURATION_MS);
    }

    private void processTranscript(int sessionId, String transcript, String audioPath) {
        if (!isSessionActive(sessionId)) return;
        boolean important = isImportant(transcript);

        CallRecord record = new CallRecord();
        record.callerName = currentCaller;
        record.platform = currentPlatform;
        record.transcript = transcript == null ? "" : transcript;
        record.audioPath = audioPath == null ? "" : audioPath;
        record.timestamp = System.currentTimeMillis();
        record.isImportant = important;
        record.isRead = false;

        long id = callLogDb.insertCallRecord(record);
        record.id = id;
        windowsSync.syncRecord(record);
        broadcastRecord(id, important);

        String confirmation = important
            ? "Your message is marked important. Pavan will be notified."
            : "Your message has been recorded. Thank you.";
        tts.refreshVoicePreference();
        tts.speak(confirmation, () -> endCurrentCall(sessionId));
    }

    private boolean isImportant(String text) {
        if (text == null || text.isEmpty()) return false;
        String lower = text.toLowerCase();
        String[] keywords = new String[]{
            "urgent", "important", "record", "note", "remind", "critical", "asap", "immediately"
        };
        for (String keyword : keywords) {
            if (lower.contains(keyword)) return true;
        }
        return false;
    }

    @SuppressLint("MissingPermission")
    private void endCurrentCall(int sessionId) {
        if (!isSessionActive(sessionId)) return;
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P && hasPermission(Manifest.permission.ANSWER_PHONE_CALLS)) {
                TelecomManager telecomManager = (TelecomManager) getSystemService(TELECOM_SERVICE);
                telecomManager.endCall();
            }
        } catch (Exception ignored) {
        } finally {
            clearActiveSession(true);
            updateNotification("Monitoring incoming calls");
        }
    }

    private void onCallEnded() {
        clearActiveSession(true);
        updateNotification("Monitoring incoming calls");
    }

    private synchronized int beginNewSession(String platform, String caller) {
        if (recording) {
            try {
                voskEngine.stopListening();
            } catch (Exception ignored) {
            }
            recording = false;
        }
        activeSessionId += 1;
        callInProgress = true;
        currentPlatform = platform;
        currentCaller = caller;
        return activeSessionId;
    }

    private synchronized boolean isSessionActive(int sessionId) {
        return callInProgress && sessionId == activeSessionId;
    }

    private synchronized void invalidateSession() {
        activeSessionId += 1;
        callInProgress = false;
    }

    private void clearActiveSession(boolean resetAudio) {
        invalidateSession();
        handler.removeCallbacksAndMessages(null);
        if (recording) {
            try {
                voskEngine.stopListening();
            } catch (Exception ignored) {
            }
            recording = false;
        }
        tts.stop();
        if (resetAudio) {
            try {
                audioManager.setSpeakerphoneOn(false);
                audioManager.setMode(AudioManager.MODE_NORMAL);
            } catch (Exception ignored) {
            }
        }
    }

    private SharedPreferences getPrefs() {
        return getSharedPreferences("jarvis_prefs", MODE_PRIVATE);
    }

    private boolean hasPermission(String permission) {
        return ContextCompat.checkSelfPermission(this, permission) == PackageManager.PERMISSION_GRANTED;
    }

    private void broadcastRecord(long recordId, boolean important) {
        Intent intent = new Intent(ACTION_NEW_RECORD);
        intent.setPackage(getPackageName());
        intent.putExtra("record_id", recordId);
        intent.putExtra("important", important);
        sendBroadcast(intent);
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationChannel channel = new NotificationChannel(
            CHANNEL_ID,
            "JARVIS Call Assistant",
            NotificationManager.IMPORTANCE_LOW
        );
        channel.setShowBadge(false);
        channel.enableVibration(false);
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(channel);
    }

    private Notification buildNotification(String status) {
        return new NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("JARVIS Call Guard")
            .setContentText(status)
            .setSmallIcon(android.R.drawable.ic_menu_call)
            .setOngoing(true)
            .setSilent(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build();
    }

    private void updateNotification(String status) {
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        manager.notify(NOTIFICATION_ID, buildNotification(status));
    }

    @Override
    public void onDestroy() {
        try {
            unregisterReceiver(callReceiver);
        } catch (Exception ignored) {
        }
        if (wakeLock != null && wakeLock.isHeld()) {
            wakeLock.release();
        }
        clearActiveSession(true);
        voskEngine.shutdown();
        tts.shutdown();
        super.onDestroy();
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
