import 'package:flutter/material.dart';

import 'package:frontend_flutter/data/models/app_notification.dart';
import 'package:frontend_flutter/data/services/api_service.dart';
import 'package:frontend_flutter/design_system/design_system.dart';

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({
    super.key,
    this.isActive = true,
    this.refreshToken = 0,
    this.onTaskChanged,
    this.onUnreadChanged,
  });

  final bool isActive;
  final int refreshToken;
  final VoidCallback? onTaskChanged;
  final ValueChanged<bool>? onUnreadChanged;

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  bool _loading = true;
  String? _error;
  List<AppNotification> _notifications = [];

  @override
  void initState() {
    super.initState();
    _load(markAsRead: widget.isActive);
  }

  @override
  void didUpdateWidget(covariant NotificationsScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.refreshToken != widget.refreshToken ||
        (!oldWidget.isActive && widget.isActive)) {
      _load(markAsRead: widget.isActive);
    }
  }

  Future<void> _load({bool markAsRead = false}) async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final notifications = await ApiService.getNotifications();
      var hasUnread = notifications.any(
        (notification) => notification.readAt == null,
      );
      if (hasUnread && markAsRead) {
        try {
          await ApiService.markAllNotificationsRead();
          hasUnread = false;
        } catch (_) {
          // The list remains usable; keep the badge until marking succeeds.
        }
      }
      if (!mounted) return;
      setState(() {
        _notifications = notifications;
        _loading = false;
      });
      widget.onUnreadChanged?.call(hasUnread);
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = 'Không thể tải lịch sử thông báo. Hãy thử lại.';
      });
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('Thông báo'),
      actions: [
        IconButton(
          onPressed: _loading ? null : () => _load(markAsRead: widget.isActive),
          tooltip: 'Làm mới',
          icon: const Icon(Icons.refresh_rounded),
        ),
        const SizedBox(width: 6),
      ],
    ),
    body: _loading
        ? const Center(child: CircularProgressIndicator())
        : _error != null
        ? _NotificationError(
            message: _error!,
            onRetry: () => _load(markAsRead: widget.isActive),
          )
        : RefreshIndicator(
            onRefresh: () => _load(markAsRead: widget.isActive),
            child: _notifications.isEmpty
                ? const _NotificationEmpty()
                : ListView.separated(
                    padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
                    itemCount: _notifications.length + 1,
                    separatorBuilder: (_, _) => const SizedBox(height: 10),
                    itemBuilder: (context, index) {
                      if (index == 0) return const _NotificationIntro();
                      return _NotificationCard(
                        notification: _notifications[index - 1],
                        onResolved: (confirmed) async {
                          final recommendation =
                              _notifications[index - 1].recommendation;
                          if (recommendation == null) return;
                          await ApiService.resolveAssistantAction(
                            recommendation.pendingActionId,
                            confirmed,
                          );
                          if (confirmed) widget.onTaskChanged?.call();
                          await _load(markAsRead: widget.isActive);
                        },
                      );
                    },
                  ),
          ),
  );
}

class _NotificationIntro extends StatelessWidget {
  const _NotificationIntro();

  @override
  Widget build(BuildContext context) => Container(
    margin: const EdgeInsets.only(bottom: 10),
    padding: const EdgeInsets.all(19),
    decoration: BoxDecoration(
      color: AppColors.mint,
      borderRadius: BorderRadius.circular(AppRadius.card),
    ),
    child: const Row(
      children: [
        Icon(
          Icons.notifications_active_outlined,
          color: AppColors.forest,
          size: 27,
        ),
        SizedBox(width: 13),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Nhắc việc & thời tiết',
                style: TextStyle(
                  fontWeight: FontWeight.w800,
                  color: AppColors.ink,
                ),
              ),
              SizedBox(height: 3),
              Text(
                'AgriMind lưu các cảnh báo đã gửi đến bạn tại đây.',
                style: TextStyle(
                  color: AppColors.muted,
                  fontSize: 12,
                  height: 1.35,
                ),
              ),
            ],
          ),
        ),
      ],
    ),
  );
}

class _NotificationCard extends StatefulWidget {
  const _NotificationCard({
    required this.notification,
    required this.onResolved,
  });

  final AppNotification notification;
  final Future<void> Function(bool confirmed) onResolved;

  @override
  State<_NotificationCard> createState() => _NotificationCardState();
}

class _NotificationCardState extends State<_NotificationCard> {
  bool _busy = false;

  Future<void> _resolve(bool confirmed) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await widget.onResolved(confirmed);
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Không thể cập nhật đề xuất. Hãy thử lại.'),
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final notification = widget.notification;
    final isWeather = notification.kind == 'weather_alert';
    final recommendation = notification.recommendation;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(15),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 43,
              height: 43,
              decoration: BoxDecoration(
                color: isWeather
                    ? AppColors.warningSurfaceStrong
                    : AppColors.mint,
                borderRadius: BorderRadius.circular(AppRadius.control),
              ),
              child: Icon(
                isWeather
                    ? Icons.thunderstorm_outlined
                    : Icons.checklist_rounded,
                color: isWeather ? AppColors.warning : AppColors.forest,
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    notification.title,
                    style: const TextStyle(
                      fontWeight: FontWeight.w800,
                      color: AppColors.ink,
                    ),
                  ),
                  const SizedBox(height: 5),
                  Text(
                    notification.body,
                    style: const TextStyle(
                      color: AppColors.muted,
                      fontSize: 13,
                      height: 1.4,
                    ),
                  ),
                  const SizedBox(height: 9),
                  Text(
                    _formatDate(notification.createdAt),
                    style: const TextStyle(
                      color: AppColors.muted,
                      fontSize: 11,
                    ),
                  ),
                  if (recommendation != null) ...[
                    const SizedBox(height: AppSpacing.sm),
                    if (recommendation.isPending && !recommendation.isExpired)
                      Row(
                        children: [
                          Expanded(
                            child: OutlinedButton(
                              onPressed: _busy ? null : () => _resolve(false),
                              child: const Text('Bỏ qua'),
                            ),
                          ),
                          const SizedBox(width: AppSpacing.xs),
                          Expanded(
                            child: FilledButton(
                              onPressed: _busy ? null : () => _resolve(true),
                              child: const Text('Tạo việc'),
                            ),
                          ),
                        ],
                      )
                    else
                      Text(
                        _recommendationStatus(recommendation),
                        style: const TextStyle(
                          color: AppColors.forest,
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _formatDate(DateTime? date) {
    if (date == null) return 'Không rõ thời điểm';
    final now = DateTime.now();
    final dayDifference = DateTime(
      now.year,
      now.month,
      now.day,
    ).difference(DateTime(date.year, date.month, date.day)).inDays;
    final time =
        '${date.hour.toString().padLeft(2, '0')}:${date.minute.toString().padLeft(2, '0')}';
    if (dayDifference == 0) return 'Hôm nay • $time';
    if (dayDifference == 1) return 'Hôm qua • $time';
    return '${date.day.toString().padLeft(2, '0')}/${date.month.toString().padLeft(2, '0')}/${date.year}';
  }

  String _recommendationStatus(NotificationRecommendation recommendation) {
    if (recommendation.isExpired || recommendation.status == 'expired') {
      return 'Đề xuất đã hết hạn';
    }
    return switch (recommendation.status) {
      'accepted' => 'Đã tạo công việc',
      'dismissed' => 'Đã bỏ qua đề xuất',
      _ => 'Đề xuất đã được xử lý',
    };
  }
}

class _NotificationEmpty extends StatelessWidget {
  const _NotificationEmpty();

  @override
  Widget build(BuildContext context) => ListView(
    children: const [
      SizedBox(height: 120),
      Icon(Icons.notifications_none_rounded, size: 52, color: AppColors.muted),
      SizedBox(height: 15),
      Text(
        'Chưa có thông báo nào',
        textAlign: TextAlign.center,
        style: TextStyle(
          fontWeight: FontWeight.w800,
          color: AppColors.ink,
          fontSize: 17,
        ),
      ),
      SizedBox(height: 7),
      Padding(
        padding: EdgeInsets.symmetric(horizontal: 42),
        child: Text(
          'Khi có việc đến hạn hoặc cảnh báo thời tiết, AgriMind sẽ hiển thị tại đây.',
          textAlign: TextAlign.center,
          style: TextStyle(color: AppColors.muted, height: 1.4),
        ),
      ),
    ],
  );
}

class _NotificationError extends StatelessWidget {
  const _NotificationError({required this.message, required this.onRetry});
  final String message;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) => Center(
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Icon(Icons.cloud_off_outlined, size: 46, color: AppColors.muted),
        const SizedBox(height: 14),
        Text(
          message,
          textAlign: TextAlign.center,
          style: const TextStyle(color: AppColors.muted),
        ),
        const SizedBox(height: 14),
        OutlinedButton.icon(
          onPressed: onRetry,
          icon: const Icon(Icons.refresh_rounded),
          label: const Text('Thử lại'),
        ),
      ],
    ),
  );
}
