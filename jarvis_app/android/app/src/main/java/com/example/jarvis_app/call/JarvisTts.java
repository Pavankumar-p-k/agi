package com.example.jarvis_app.call;

import android.content.Context;
import android.content.SharedPreferences;
import android.media.AudioAttributes;
import android.media.AudioManager;
import android.os.Build;
import android.os.Bundle;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.speech.tts.Voice;

import java.util.HashMap;
import java.util.Locale;
import java.util.Set;

public class JarvisTts {
    private static final String PREFS_NAME = "jarvis_prefs";
    private static final String PREF_CALL_AUDIO_MODE = "call_audio_mode";
    private TextToSpeech tts;
    private boolean ready = false;
    private final Context appContext;
    private static int utteranceCounter = 0;
    private String pendingText;
    private DoneCallback pendingCallback;
    private static final String[] MALE_HINTS = new String[]{
        "male", "m1", "m2", "iob", "ioc", "iod", "iol", "iom"
    };
    private static final String[] FEMALE_HINTS = new String[]{
        "female", "f1", "f2", "ioa", "iof", "iog", "ioh", "ioj", "iok"
    };

    public interface DoneCallback {
        void onDone();
    }

    public JarvisTts(Context context) {
        appContext = context.getApplicationContext();
        tts = new TextToSpeech(context, status -> {
            if (status == TextToSpeech.SUCCESS) {
                tts.setLanguage(Locale.US);
                tts.setSpeechRate(0.90f);
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                    AudioAttributes attrs = new AudioAttributes.Builder()
                        .setUsage(isRemoteAudioMode() ? AudioAttributes.USAGE_MEDIA : AudioAttributes.USAGE_VOICE_COMMUNICATION)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build();
                    tts.setAudioAttributes(attrs);
                }
                applyVoicePreference();
                ready = true;
                if (pendingText != null) {
                    String text = pendingText;
                    DoneCallback callback = pendingCallback;
                    pendingText = null;
                    pendingCallback = null;
                    speak(text, callback);
                }
            } else if (pendingCallback != null) {
                pendingCallback.onDone();
                pendingText = null;
                pendingCallback = null;
            }
        });
    }

    public void refreshVoicePreference() {
        if (!ready) return;
        applyVoicePreference();
    }

    private boolean isRemoteAudioMode() {
        SharedPreferences prefs = appContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        String saved = prefs.getString(PREF_CALL_AUDIO_MODE, "remote");
        return saved == null || !"local".equalsIgnoreCase(saved);
    }

    private void applyVoicePreference() {
        boolean voiceSet = trySetVoice();
        tts.setSpeechRate(0.90f);
        tts.setPitch(voiceSet ? 0.70f : 0.65f);
    }

    private boolean trySetVoice() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.LOLLIPOP) {
            return false;
        }
        try {
            Set<Voice> voices = tts.getVoices();
            if (voices == null || voices.isEmpty()) return false;

            Voice best = null;
            int bestScore = Integer.MIN_VALUE;

            for (Voice voice : voices) {
                if (voice == null || voice.getLocale() == null) continue;
                Locale locale = voice.getLocale();
                if (!"en".equalsIgnoreCase(locale.getLanguage())) continue;
                if (voice.getFeatures() != null && voice.getFeatures().contains("notInstalled")) continue;

                String name = voice.getName() == null ? "" : voice.getName().toLowerCase(Locale.US);
                int score = 0;
                if ("US".equalsIgnoreCase(locale.getCountry())) score += 20;
                if (!voice.isNetworkConnectionRequired()) score += 10;

                for (String hint : MALE_HINTS) {
                    if (name.contains(hint)) {
                        score += 45;
                        break;
                    }
                }
                for (String hint : FEMALE_HINTS) {
                    if (name.contains(hint)) {
                        score -= 60;
                        break;
                    }
                }

                if (score > bestScore) {
                    bestScore = score;
                    best = voice;
                }
            }

            if (best != null) {
                return tts.setVoice(best) == TextToSpeech.SUCCESS;
            }
        } catch (Exception ignored) {
        }
        return false;
    }

    public void speak(String text, DoneCallback callback) {
        if (!ready) {
            pendingText = text;
            pendingCallback = callback;
            return;
        }

        refreshVoicePreference();
        String utteranceId = "jarvis_" + utteranceCounter++;
        tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
            @Override
            public void onStart(String id) {}

            @Override
            public void onDone(String id) {
                if (utteranceId.equals(id) && callback != null) {
                    callback.onDone();
                }
            }

            @Override
            public void onError(String id) {
                if (utteranceId.equals(id) && callback != null) {
                    callback.onDone();
                }
            }
        });

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            Bundle params = new Bundle();
            params.putInt(
                TextToSpeech.Engine.KEY_PARAM_STREAM,
                isRemoteAudioMode() ? AudioManager.STREAM_MUSIC : AudioManager.STREAM_VOICE_CALL
            );
            tts.speak(text, TextToSpeech.QUEUE_FLUSH, params, utteranceId);
        } else {
            HashMap<String, String> params = new HashMap<>();
            params.put(TextToSpeech.Engine.KEY_PARAM_UTTERANCE_ID, utteranceId);
            params.put(
                TextToSpeech.Engine.KEY_PARAM_STREAM,
                String.valueOf(isRemoteAudioMode() ? AudioManager.STREAM_MUSIC : AudioManager.STREAM_VOICE_CALL)
            );
            tts.speak(text, TextToSpeech.QUEUE_FLUSH, params);
        }
    }

    public void shutdown() {
        tts.shutdown();
    }

    public void stop() {
        try {
            pendingText = null;
            pendingCallback = null;
            tts.stop();
        } catch (Exception ignored) {
        }
    }
}
