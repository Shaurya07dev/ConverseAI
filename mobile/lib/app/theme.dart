import "package:flutter/material.dart";

class VaakSetuColors {
  static const background = Color(0xFF0A0A09);
  static const surface = Color(0xFF11110F);
  static const surfaceElevated = Color(0xFF181816);

  static const orange = Color(0xFFFF7618);
  static const orangeDark = Color(0xFFD85B0A);

  static const primaryText = Color(0xFFF5F2ED);
  static const secondaryText = Color(0xFF9A9894);
  static const mutedText = Color(0xFF62605C);

  static const border = Color(0xFF292825);
}

class VaakSetuTheme {
  static ThemeData dark() {
    return ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: VaakSetuColors.background,

      colorScheme: const ColorScheme.dark(
        primary: VaakSetuColors.orange,
        surface: VaakSetuColors.surface,
      ),

      appBarTheme: const AppBarTheme(
        backgroundColor: Colors.transparent,
        elevation: 0,
        foregroundColor: VaakSetuColors.primaryText,
      ),

      textTheme: const TextTheme(
        displayLarge: TextStyle(
          color: VaakSetuColors.primaryText,
          fontSize: 42,
          fontWeight: FontWeight.w700,
          height: 1.05,
        ),
        headlineMedium: TextStyle(
          color: VaakSetuColors.primaryText,
          fontSize: 20,
          fontWeight: FontWeight.w600,
        ),
        titleLarge: TextStyle(
          color: VaakSetuColors.primaryText,
          fontSize: 20,
          fontWeight: FontWeight.w600,
        ),
        bodyLarge: TextStyle(
          color: VaakSetuColors.primaryText,
          fontSize: 16,
          height: 1.5,
        ),
        bodyMedium: TextStyle(
          color: VaakSetuColors.secondaryText,
          fontSize: 14,
          height: 1.5,
        ),
        labelMedium: TextStyle(
          color: VaakSetuColors.secondaryText,
          fontSize: 12,
          letterSpacing: 1.5,
        ),
      ),

      dividerTheme: const DividerThemeData(
        color: VaakSetuColors.border,
      ),
    );
  }
}