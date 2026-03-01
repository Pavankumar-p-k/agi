package com.example.jarvis_app.wishes;

import java.util.Calendar;

public class WishEngine {
    public String getWish(String callerName) {
        StringBuilder message = new StringBuilder();
        message.append(getTimeGreeting());
        if (callerName != null && !callerName.isEmpty() && !"Unknown".equals(callerName) && !callerName.matches("[+\\d].*")) {
            message.append(", ").append(callerName);
        }
        message.append(". ");

        String special = getSpecialDayWish();
        if (special != null) {
            message.append(special).append(". ");
        } else {
            String dayContext = getDayContext();
            if (dayContext != null) {
                message.append(dayContext).append(". ");
            }
        }
        return message.toString().trim();
    }

    private String getTimeGreeting() {
        int hour = Calendar.getInstance().get(Calendar.HOUR_OF_DAY);
        if (hour >= 5 && hour < 12) return "Good morning";
        if (hour >= 12 && hour < 17) return "Good afternoon";
        if (hour >= 17 && hour < 21) return "Good evening";
        return "Good night";
    }

    private String getDayContext() {
        int day = Calendar.getInstance().get(Calendar.DAY_OF_WEEK);
        if (day == Calendar.FRIDAY) return "Happy Friday";
        if (day == Calendar.SATURDAY || day == Calendar.SUNDAY) return "Enjoy your weekend";
        return null;
    }

    private String getSpecialDayWish() {
        Calendar calendar = Calendar.getInstance();
        int month = calendar.get(Calendar.MONTH) + 1;
        int day = calendar.get(Calendar.DAY_OF_MONTH);

        if (month == 1 && day == 1) return "Happy New Year";
        if (month == 1 && day == 26) return "Happy Republic Day";
        if (month == 8 && day == 15) return "Happy Independence Day";
        if (month == 10 && day == 2) return "Happy Gandhi Jayanti";
        if (month == 12 && day == 25) return "Merry Christmas";

        // Approximate date windows for mobile-only greeting behavior.
        if (month == 3 && day >= 24 && day <= 26) return "Happy Holi";
        if ((month == 10 && day >= 25) || (month == 11 && day <= 5)) return "Happy Diwali";
        return null;
    }
}
