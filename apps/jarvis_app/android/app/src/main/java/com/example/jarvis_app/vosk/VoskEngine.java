// android/app/src/main/java/com/jarvis/app/vosk/VoskEngine.java
//
// Offline Speech-to-Text using Vosk
// Records caller's audio → converts to text → no internet needed
//
// Setup:
//  1. Download vosk model: https://alphacephei.com/vosk/models
//     Recommended: vosk-model-small-en-in-0.4  (Indian English, 39MB)
//  2. Place in: android/app/src/main/assets/vosk-model/
//  3. Add to build.gradle: implementation 'com.alphacephei:vosk-android:0.3.47'

package com.example.jarvis_app.vosk;

import android.content.Context;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.os.AsyncTask;
import android.util.Log;

import org.vosk.Model;
import org.vosk.Recognizer;
import org.vosk.android.SpeechService;
import org.vosk.android.RecognitionListener;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;

public class VoskEngine {
    private static final String TAG = "VoskEngine";

    private final Context _ctx;
    private Model _model;
    private SpeechService _speechSvc;
    private boolean _ready = false;

    public interface ResultCallback {
        void onPartialResult(String text);
        void onFinalResult(String transcript);
        void onError(String error);
    }

    public VoskEngine(Context ctx) {
        _ctx = ctx;
        loadModelAsync();
    }

    private void loadModelAsync() {
        new Thread(() -> {
            try {
                File modelDir = new File(_ctx.getFilesDir(), "vosk-model");
                if (!modelDir.exists()) {
                    // Copy from assets
                    copyAssets("vosk-model", modelDir);
                }
                _model = new Model(modelDir.getAbsolutePath());
                _ready = true;
                Log.d(TAG, "Vosk model loaded ✓");
            } catch (Throwable t) {
                // Vosk uses native libraries (JNA). If the platform does not support
                // the required native bindings, it can throw UnsatisfiedLinkError.
                // We catch Throwable to prevent the whole app from crashing.
                Log.e(TAG, "Vosk model load failed", t);
            }
        }, "VoskModelLoader").start();
    }

    private void copyAssets(String assetDir, File targetDir) throws IOException {
        targetDir.mkdirs();
        String[] assets = _ctx.getAssets().list(assetDir);
        if (assets == null) return;
        for (String asset : assets) {
            File target = new File(targetDir, asset);
            String assetPath = assetDir + "/" + asset;
            String[] subAssets = _ctx.getAssets().list(assetPath);
            if (subAssets != null && subAssets.length > 0) {
                copyAssets(assetPath, target);
            } else {
                try (InputStream in = _ctx.getAssets().open(assetPath);
                     FileOutputStream out = new FileOutputStream(target)) {
                    byte[] buf = new byte[4096];
                    int n;
                    while ((n = in.read(buf)) != -1) out.write(buf, 0, n);
                }
            }
        }
    }

    public void startListening(File audioFile, ResultCallback cb) {
        if (!_ready || _model == null) {
            cb.onError("Vosk model not ready");
            return;
        }
        try {
            Recognizer rec = new Recognizer(_model, 16000.0f);
            _speechSvc = new SpeechService(rec, 16000.0f);
            _speechSvc.startListening(new RecognitionListener() {
                @Override
                public void onPartialResult(String hypothesis) {
                    String text = parseHypothesis(hypothesis);
                    cb.onPartialResult(text);
                }

                @Override
                public void onResult(String hypothesis) {
                    String text = parseHypothesis(hypothesis);
                    if (!text.isEmpty()) {
                        cb.onFinalResult(text);
                    }
                }

                @Override
                public void onFinalResult(String hypothesis) {
                    String text = parseHypothesis(hypothesis);
                    cb.onFinalResult(text);
                }

                @Override
                public void onError(Exception e) {
                    cb.onError(e.getMessage());
                }

                @Override
                public void onTimeout() {
                    cb.onFinalResult("");
                }
            });
            Log.d(TAG, "Vosk listening started ✓");
        } catch (Exception e) {
            Log.e(TAG, "Start listening failed: " + e);
            cb.onError(e.getMessage());
        }
    }

    private String parseHypothesis(String json) {
        // Vosk returns JSON like: {"text": "hello world"}
        if (json == null) return "";
        try {
            int start = json.indexOf("\"text\"");
            if (start < 0) return "";
            int q1 = json.indexOf("\"", start + 7);
            int q2 = json.indexOf("\"", q1 + 1);
            if (q1 >= 0 && q2 > q1) return json.substring(q1 + 1, q2);
        } catch (Exception ignored) {}
        return "";
    }

    public void stopListening() {
        if (_speechSvc != null) {
            _speechSvc.stop();
            Log.d(TAG, "Vosk listening stopped");
        }
    }

    public void shutdown() {
        stopListening();
        if (_speechSvc != null) _speechSvc.shutdown();
    }

    public boolean isReady() { return _ready; }
}
