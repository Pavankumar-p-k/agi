package com.example.jarvis_app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

import com.example.jarvis_app.call.CallAssistantService;

public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent.getAction();
        if (!Intent.ACTION_BOOT_COMPLETED.equals(action) && !Intent.ACTION_MY_PACKAGE_REPLACED.equals(action)) {
            return;
        }
        boolean enabled = context.getSharedPreferences("jarvis_prefs", Context.MODE_PRIVATE)
            .getBoolean("call_guard_autostart", false);
        if (!enabled) {
            return;
        }

        Intent serviceIntent = new Intent(context, CallAssistantService.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(serviceIntent);
        } else {
            context.startService(serviceIntent);
        }
    }
}
