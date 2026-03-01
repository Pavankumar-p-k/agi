// lib/theme/app_theme.dart
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class JarvisColors {
  // Core palette
  static const bg         = Color(0xFF010A12);
  static const bgCard     = Color(0xFF061420);
  static const bgPanel    = Color(0xFF0A1E2E);
  static const cyan       = Color(0xFF00E5FF);
  static const cyanDim    = Color(0xFF0097A7);
  static const blue       = Color(0xFF0066FF);
  static const blueDark   = Color(0xFF003380);
  static const green      = Color(0xFF00FFAA);
  static const greenDim   = Color(0xFF00897B);
  static const orange     = Color(0xFFFF6A00);
  static const red        = Color(0xFFFF1744);
  static const textPrimary   = Color(0xFFB0EEFF);
  static const textSecondary = Color(0xFF4A7A8A);
  static const textDim       = Color(0xFF1E4A5A);
  static const border        = Color(0xFF0D3348);
  static const borderBright  = Color(0xFF1A6680);
}

class AppTheme {
  static ThemeData get dark {
    return ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: JarvisColors.bg,
      colorScheme: const ColorScheme.dark(
        primary: JarvisColors.cyan,
        secondary: JarvisColors.blue,
        surface: JarvisColors.bgCard,
        error: JarvisColors.red,
      ),
      textTheme: TextTheme(
        displayLarge: GoogleFonts.orbitron(
          fontSize: 32, fontWeight: FontWeight.w900,
          color: JarvisColors.cyan, letterSpacing: 4,
        ),
        displayMedium: GoogleFonts.orbitron(
          fontSize: 24, fontWeight: FontWeight.w700,
          color: JarvisColors.cyan, letterSpacing: 3,
        ),
        displaySmall: GoogleFonts.orbitron(
          fontSize: 18, fontWeight: FontWeight.w600,
          color: JarvisColors.textPrimary, letterSpacing: 2,
        ),
        headlineMedium: GoogleFonts.orbitron(
          fontSize: 14, fontWeight: FontWeight.w600,
          color: JarvisColors.cyan, letterSpacing: 2,
        ),
        bodyLarge: GoogleFonts.shareTech(
          fontSize: 16, color: JarvisColors.textPrimary, letterSpacing: 0.5,
        ),
        bodyMedium: GoogleFonts.shareTech(
          fontSize: 14, color: JarvisColors.textPrimary, letterSpacing: 0.3,
        ),
        bodySmall: GoogleFonts.shareTech(
          fontSize: 12, color: JarvisColors.textSecondary, letterSpacing: 0.5,
        ),
        labelSmall: GoogleFonts.orbitron(
          fontSize: 10, color: JarvisColors.textSecondary, letterSpacing: 1.5,
        ),
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: JarvisColors.bg,
        elevation: 0,
        centerTitle: true,
        titleTextStyle: GoogleFonts.orbitron(
          fontSize: 16, fontWeight: FontWeight.w700,
          color: JarvisColors.cyan, letterSpacing: 3,
        ),
        iconTheme: const IconThemeData(color: JarvisColors.cyan),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: JarvisColors.bgPanel,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(4),
          borderSide: const BorderSide(color: JarvisColors.border, width: 1),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(4),
          borderSide: const BorderSide(color: JarvisColors.border, width: 1),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(4),
          borderSide: const BorderSide(color: JarvisColors.cyan, width: 1.5),
        ),
        hintStyle: GoogleFonts.shareTech(color: JarvisColors.textDim),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: JarvisColors.blue,
          foregroundColor: JarvisColors.cyan,
          textStyle: GoogleFonts.orbitron(fontSize: 12, letterSpacing: 2),
          shape: const RoundedRectangleBorder(borderRadius: BorderRadius.zero),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
        ),
      ),
      bottomNavigationBarTheme: BottomNavigationBarThemeData(
        backgroundColor: JarvisColors.bgCard,
        selectedItemColor: JarvisColors.cyan,
        unselectedItemColor: JarvisColors.textSecondary,
        selectedLabelStyle: GoogleFonts.orbitron(fontSize: 9, letterSpacing: 1),
        unselectedLabelStyle: GoogleFonts.orbitron(fontSize: 9, letterSpacing: 1),
        type: BottomNavigationBarType.fixed,
        elevation: 0,
      ),
      cardTheme: CardThemeData(
        color: JarvisColors.bgCard,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(4),
          side: const BorderSide(color: JarvisColors.border, width: 1),
        ),
        margin: const EdgeInsets.all(0),
      ),
    );
  }
}
