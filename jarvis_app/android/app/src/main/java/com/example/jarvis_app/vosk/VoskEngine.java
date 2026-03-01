package com.example.jarvis_app.vosk;

import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.util.Log;

import org.vosk.Model;
import org.vosk.Recognizer;
import org.vosk.android.SpeechService;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Locale;

public class VoskEngine {
    private static final String TAG = "VoskEngine";

    public interface ResultCallback {
        void onPartialResult(String text);
        void onFinalResult(String transcript, String audioPath);
        void onError(String error);
    }

    private final Context context;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private volatile boolean ready = false;
    private volatile boolean usingFallback = false;
    private Model model;
    private SpeechService speechService;
    private SpeechRecognizer fallbackRecognizer;

    public VoskEngine(Context context) {
        this.context = context.getApplicationContext();
        loadModelAsync();
    }

    public boolean isReady() {
        return ready;
    }

    public void startListening(ResultCallback callback) {
        if (!ready) {
            callback.onError("Speech engine is not ready");
            return;
        }
        if (usingFallback || model == null) {
            startFallbackListening(callback);
            return;
        }
        stopListening();
        try {
            Recognizer recognizer = new Recognizer(model, 16000.0f);
            speechService = new SpeechService(recognizer, 16000.0f);
            speechService.startListening(new org.vosk.android.RecognitionListener() {
                @Override
                public void onPartialResult(String hypothesis) {
                    callback.onPartialResult(parseText(hypothesis));
                }

                @Override
                public void onResult(String hypothesis) {
                    String text = parseText(hypothesis);
                    if (!text.isEmpty()) {
                        callback.onFinalResult(text, "");
                    }
                }

                @Override
                public void onFinalResult(String hypothesis) {
                    callback.onFinalResult(parseText(hypothesis), "");
                }

                @Override
                public void onError(Exception e) {
                    callback.onError(e.getMessage() == null ? "Unknown error" : e.getMessage());
                }

                @Override
                public void onTimeout() {
                    callback.onFinalResult("", "");
                }
            });
        } catch (Throwable ex) {
            callback.onError(ex.getMessage() == null ? "Start failed" : ex.getMessage());
        }
    }

    public void stopListening() {
        if (speechService != null) {
            speechService.stop();
        }
        if (fallbackRecognizer != null) {
            try {
                fallbackRecognizer.stopListening();
                fallbackRecognizer.cancel();
            } catch (Exception ignored) {
            }
        }
    }

    public void shutdown() {
        stopListening();
        if (speechService != null) {
            speechService.shutdown();
            speechService = null;
        }
        if (model != null) {
            model.close();
            model = null;
        }
        mainHandler.post(() -> {
            if (fallbackRecognizer != null) {
                try {
                    fallbackRecognizer.destroy();
                } catch (Exception ignored) {
                }
                fallbackRecognizer = null;
            }
        });
    }

    private void loadModelAsync() {
        new Thread(() -> {
            try {
                File modelDir = new File(context.getFilesDir(), "vosk-model");
                if (!isValidModelDir(modelDir)) {
                    deleteRecursive(modelDir);
                    copyAssetsRecursive("vosk-model", modelDir);
                }
                model = new Model(modelDir.getAbsolutePath());
                usingFallback = false;
                ready = true;
                Log.d(TAG, "Model loaded");
            } catch (Throwable ex) {
                String msg = ex.getMessage() == null ? ex.toString() : ex.getMessage();
                Log.e(TAG, "Model load failed: " + msg, ex);
                enableFallback();
            }
        }, "VoskModelLoader").start();
    }

    private void enableFallback() {
        if (!SpeechRecognizer.isRecognitionAvailable(context)) {
            usingFallback = false;
            ready = false;
            Log.e(TAG, "SpeechRecognizer fallback is not available on this device");
            return;
        }
        usingFallback = true;
        ready = true;
        Log.w(TAG, "Using Android SpeechRecognizer fallback");
    }

    private void ensureFallbackRecognizer() {
        if (fallbackRecognizer == null) {
            fallbackRecognizer = SpeechRecognizer.createSpeechRecognizer(context);
        }
    }

    private void startFallbackListening(ResultCallback callback) {
        mainHandler.post(() -> {
            try {
                ensureFallbackRecognizer();
                final boolean[] deliveredFinal = new boolean[]{false};
                fallbackRecognizer.setRecognitionListener(new RecognitionListener() {
                    @Override
                    public void onReadyForSpeech(Bundle params) {
                        // No-op.
                    }

                    @Override
                    public void onBeginningOfSpeech() {
                        // No-op.
                    }

                    @Override
                    public void onRmsChanged(float rmsdB) {
                        // No-op.
                    }

                    @Override
                    public void onBufferReceived(byte[] buffer) {
                        // No-op.
                    }

                    @Override
                    public void onEndOfSpeech() {
                        // No-op.
                    }

                    @Override
                    public void onError(int error) {
                        if (deliveredFinal[0]) return;
                        callback.onError("Speech error " + error);
                    }

                    @Override
                    public void onResults(Bundle results) {
                        if (deliveredFinal[0]) return;
                        deliveredFinal[0] = true;
                        callback.onFinalResult(extractSpeechResult(results), "");
                    }

                    @Override
                    public void onPartialResults(Bundle partialResults) {
                        callback.onPartialResult(extractSpeechResult(partialResults));
                    }

                    @Override
                    public void onEvent(int eventType, Bundle params) {
                        // No-op.
                    }
                });

                Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
                intent.putExtra(
                    RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                    RecognizerIntent.LANGUAGE_MODEL_FREE_FORM
                );
                intent.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true);
                intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1);
                intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.getDefault().toString());
                intent.putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, false);
                fallbackRecognizer.startListening(intent);
            } catch (Throwable ex) {
                callback.onError(ex.getMessage() == null ? "Speech fallback start failed" : ex.getMessage());
            }
        });
    }

    private String extractSpeechResult(Bundle bundle) {
        if (bundle == null) return "";
        ArrayList<String> list = bundle.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
        if (list == null || list.isEmpty()) return "";
        String text = list.get(0);
        return text == null ? "" : text.trim();
    }

    private boolean isValidModelDir(File modelDir) {
        if (modelDir == null || !modelDir.exists() || !modelDir.isDirectory()) return false;
        File am = new File(modelDir, "am/final.mdl");
        File conf = new File(modelDir, "conf/model.conf");
        File graph = new File(modelDir, "graph/HCLr.fst");
        File ivector = new File(modelDir, "ivector/final.ie");
        return am.exists() && conf.exists() && graph.exists() && ivector.exists();
    }

    private void deleteRecursive(File path) {
        if (path == null || !path.exists()) return;
        if (path.isDirectory()) {
            File[] children = path.listFiles();
            if (children != null) {
                for (File child : children) {
                    deleteRecursive(child);
                }
            }
        }
        // Ignore delete result; missing file after recursion is acceptable.
        path.delete();
    }

    private void copyAssetsRecursive(String assetsPath, File targetDir) throws Exception {
        String[] entries = context.getAssets().list(assetsPath);
        if (entries == null) return;
        targetDir.mkdirs();
        for (String entry : entries) {
            String childPath = assetsPath + "/" + entry;
            String[] nested = context.getAssets().list(childPath);
            File target = new File(targetDir, entry);
            if (nested != null && nested.length > 0) {
                copyAssetsRecursive(childPath, target);
                continue;
            }
            try (InputStream in = context.getAssets().open(childPath);
                 FileOutputStream out = new FileOutputStream(target)) {
                byte[] buffer = new byte[4096];
                int read;
                while ((read = in.read(buffer)) != -1) {
                    out.write(buffer, 0, read);
                }
            }
        }
    }

    private String parseText(String json) {
        if (json == null) return "";
        int marker = json.indexOf("\"text\"");
        if (marker < 0) return "";
        int start = json.indexOf('"', marker + 7);
        int end = start >= 0 ? json.indexOf('"', start + 1) : -1;
        if (start < 0 || end <= start) return "";
        return json.substring(start + 1, end);
    }
}
