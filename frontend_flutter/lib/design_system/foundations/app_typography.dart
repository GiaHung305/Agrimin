import 'package:flutter/material.dart';

import 'app_colors.dart';

/// Product typography applied once by [buildAppTheme].
///
/// Feature widgets should start from `Theme.of(context).textTheme` and only
/// override properties that express a deliberate local hierarchy.
abstract final class AppTypography {
  static TextTheme build(TextTheme base) {
    final themed = base.apply(
      fontFamily: 'Roboto',
      bodyColor: AppColors.ink,
      displayColor: AppColors.ink,
    );

    return themed.copyWith(
      headlineSmall: themed.headlineSmall?.copyWith(
        fontWeight: FontWeight.w800,
        letterSpacing: -0.3,
      ),
      titleLarge: themed.titleLarge?.copyWith(fontWeight: FontWeight.w800),
      titleMedium: themed.titleMedium?.copyWith(fontWeight: FontWeight.w700),
      bodyLarge: themed.bodyLarge?.copyWith(height: 1.45),
      bodyMedium: themed.bodyMedium?.copyWith(height: 1.4),
      labelLarge: themed.labelLarge?.copyWith(fontWeight: FontWeight.w700),
    );
  }
}
