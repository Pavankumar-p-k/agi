// android/app/src/main/java/com/jarvis/app/wishes/WishEngine.java
//
// JARVIS WishEngine — Real-time context-aware greetings
// ──────────────────────────────────────────────────────
// Generates the right greeting based on:
//  • Current time (morning / afternoon / evening / night)
//  • Day of week (weekend / weekday)
//  • Caller name (if available from contacts)
//  • Special days (New Year, Diwali, Christmas, etc.)
//  • Indian national holidays
//
// BEFORE the default "sir is busy" message, JARVIS says:
//  "Good evening, Rahul. Happy Diwali to you! Pavan sir is busy..."
//  "Good morning! Have a great Monday. Pavan sir is currently busy..."

package com.example.jarvis_app.wishes;

import java.util.Calendar;
import java.util.HashMap;
import java.util.Map;

public class WishEngine {

    // ── Time-based greetings ──────────────────────────────
    public String getTimeGreeting() {
        int hour = Calendar.getInstance().get(Calendar.HOUR_OF_DAY);
        if (hour >= 5  && hour < 12) return "Good morning";
        if (hour >= 12 && hour < 17) return "Good afternoon";
        if (hour >= 17 && hour < 21) return "Good evening";
        return "Good night";                  // 9 PM – 5 AM
    }

    // ── Day-based context ────────────────────────────────
    public String getDayContext() {
        Calendar cal = Calendar.getInstance();
        int day  = cal.get(Calendar.DAY_OF_WEEK);
        int hour = cal.get(Calendar.HOUR_OF_DAY);

        switch (day) {
            case Calendar.MONDAY:
                return "Hope you have a productive week ahead";
            case Calendar.FRIDAY:
                return "Happy Friday";
            case Calendar.SATURDAY:
                return "Enjoy your weekend";
            case Calendar.SUNDAY:
                return "Hope you are having a relaxing Sunday";
            default:
                if (hour >= 5 && hour < 9) return "Hope you have a great day ahead";
                return null;
        }
    }

    // ── Special day detector ─────────────────────────────
    public String getSpecialDayWish() {
        Calendar cal   = Calendar.getInstance();
        int month      = cal.get(Calendar.MONTH) + 1;   // 1–12
        int dayOfMonth = cal.get(Calendar.DAY_OF_MONTH);

        // ── Fixed-date holidays ──
        // New Year
        if (month == 1 && dayOfMonth == 1)  return "Happy New Year";
        // Republic Day
        if (month == 1 && dayOfMonth == 26) return "Happy Republic Day";
        // Valentine's Day
        if (month == 2 && dayOfMonth == 14) return "Happy Valentine's Day";
        // Holi (approximate — March 25 ±2 days varies)
        if (month == 3 && dayOfMonth >= 24 && dayOfMonth <= 26) return "Happy Holi";
        // Independence Day
        if (month == 8 && dayOfMonth == 15) return "Happy Independence Day";
        // Gandhi Jayanti
        if (month == 10 && dayOfMonth == 2) return "Happy Gandhi Jayanti";
        // Halloween
        if (month == 10 && dayOfMonth == 31) return "Happy Halloween";
        // Diwali (approximate — Oct 20 – Nov 15 window, changes yearly)
        // We do a simple check for the Diwali range; use a calendar lib for exact date
        if (month == 11 && dayOfMonth >= 1 && dayOfMonth <= 5) return "Happy Diwali";
        // Christmas
        if (month == 12 && dayOfMonth == 25) return "Merry Christmas";
        if (month == 12 && dayOfMonth == 24) return "Happy Christmas Eve";
        // New Year Eve
        if (month == 12 && dayOfMonth == 31) return "Happy New Year's Eve";

        return null;   // no special day
    }

    // ── Full greeting builder ────────────────────────────
    /**
     * Builds the full opening greeting spoken BEFORE the default busy message.
     *
     * Output examples:
     *  "Good morning, Rahul. Happy New Year!"
     *  "Good evening. Happy Friday — enjoy your weekend."
     *  "Good afternoon, Priya."
     *  "Good morning. Hope you have a great day ahead."
     */
    public String getWish(String callerName) {
        StringBuilder sb = new StringBuilder();

        // 1. Time greeting
        sb.append(getTimeGreeting());

        // 2. Caller name (if not unknown number)
        if (callerName != null && !callerName.isEmpty()
                && !callerName.equals("Unknown")
                && !callerName.matches("[+\\d].*")) {   // not a raw phone number
            sb.append(", ").append(callerName);
        }

        sb.append(". ");

        // 3. Special day wish (highest priority)
        String special = getSpecialDayWish();
        if (special != null) {
            sb.append(special).append("! ");
        } else {
            // 4. Day context (only if no special day)
            String dayCtx = getDayContext();
            if (dayCtx != null) {
                sb.append(dayCtx).append(". ");
            }
        }

        return sb.toString().trim();
    }

    // ── Season detection ─────────────────────────────────
    public String getSeason() {
        int month = Calendar.getInstance().get(Calendar.MONTH) + 1;
        if (month >= 3 && month <= 5)  return "spring";
        if (month >= 6 && month <= 8)  return "summer";
        if (month >= 9 && month <= 11) return "autumn";
        return "winter";
    }
}
