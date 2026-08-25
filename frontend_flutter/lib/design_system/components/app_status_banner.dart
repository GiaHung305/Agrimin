import 'package:flutter/material.dart';

import '../foundations/app_colors.dart';
import '../foundations/app_radius.dart';
import '../foundations/app_spacing.dart';

enum AppStatusKind { info, success, warning, error }

class AppStatusBanner extends StatelessWidget {
  const AppStatusBanner({
    super.key,
    required this.message,
    this.kind = AppStatusKind.info,
  });

  const AppStatusBanner.success({super.key, required this.message})
    : kind = AppStatusKind.success;
  const AppStatusBanner.warning({super.key, required this.message})
    : kind = AppStatusKind.warning;
  const AppStatusBanner.error({super.key, required this.message})
    : kind = AppStatusKind.error;

  final String message;
  final AppStatusKind kind;

  @override
  Widget build(BuildContext context) {
    final (background, foreground, icon) = switch (kind) {
      AppStatusKind.info => (
        AppColors.mint,
        AppColors.forestDark,
        Icons.info_outline_rounded,
      ),
      AppStatusKind.success => (
        AppColors.successSurface,
        AppColors.forestDark,
        Icons.check_circle_outline_rounded,
      ),
      AppStatusKind.warning => (
        AppColors.warningSurface,
        AppColors.warningDark,
        Icons.warning_amber_rounded,
      ),
      AppStatusKind.error => (
        AppColors.dangerSurface,
        AppColors.dangerDark,
        Icons.error_outline_rounded,
      ),
    };
    return Semantics(
      liveRegion: kind == AppStatusKind.error || kind == AppStatusKind.success,
      child: Container(
        padding: const EdgeInsets.all(AppSpacing.sm),
        decoration: BoxDecoration(
          color: background,
          borderRadius: BorderRadius.circular(AppRadius.control),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: foreground, size: 20),
            const SizedBox(width: AppSpacing.xs),
            Expanded(
              child: Text(
                message,
                style: Theme.of(
                  context,
                ).textTheme.bodySmall?.copyWith(color: foreground, height: 1.4),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
