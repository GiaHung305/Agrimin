import 'package:flutter/material.dart';

Future<bool> showAppConfirmDialog({
  required BuildContext context,
  required String title,
  required String message,
  String confirmLabel = 'Xác nhận',
  String cancelLabel = 'Hủy',
  bool destructive = false,
}) async {
  final accepted = await showDialog<bool>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      title: Text(title),
      content: Text(message),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(dialogContext, false),
          child: Text(cancelLabel),
        ),
        FilledButton(
          style: destructive
              ? FilledButton.styleFrom(
                  backgroundColor: Theme.of(context).colorScheme.error,
                )
              : null,
          onPressed: () => Navigator.pop(dialogContext, true),
          child: Text(confirmLabel),
        ),
      ],
    ),
  );
  return accepted ?? false;
}

abstract final class AppSnackbar {
  static void success(BuildContext context, String message) =>
      _show(context, message, icon: Icons.check_circle_outline_rounded);

  static void error(BuildContext context, String message) =>
      _show(context, message, icon: Icons.error_outline_rounded, isError: true);

  static void info(BuildContext context, String message) =>
      _show(context, message, icon: Icons.info_outline_rounded);

  static void _show(
    BuildContext context,
    String message, {
    required IconData icon,
    bool isError = false,
  }) {
    final colors = Theme.of(context).colorScheme;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          backgroundColor: isError ? colors.error : colors.inverseSurface,
          content: Row(
            children: [
              Icon(
                icon,
                color: isError ? colors.onError : colors.onInverseSurface,
              ),
              const SizedBox(width: 12),
              Expanded(child: Text(message)),
            ],
          ),
        ),
      );
  }
}
