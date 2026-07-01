// android/app/src/main/java/com/jarvis/app/BootReceiver.java
//
// Auto-starts JarvisWakeService when the phone boots
// so JARVIS is ready even after a restart

package com.example.jarvis_app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.util.Log;

public class BootReceiver extends BroadcastReceiver {

    private static final String TAG = "JarvisBootReceiver";

    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent.getAction();

        // Disabled auto-start to avoid foreground microphone restrictions on install.
        if (Intent.ACTION_BOOT_COMPLETED.equals(action)
         || "android.intent.action.QUICKBOOT_POWERON".equals(action)) {
            Log.d(TAG, "Boot detected — wake service not auto-started (manual start only)");
        }
    }
}
