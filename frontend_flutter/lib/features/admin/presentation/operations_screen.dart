import 'dart:async';

import 'package:flutter/material.dart';

import 'package:frontend_flutter/data/models/worker_dashboard.dart';
import 'package:frontend_flutter/data/services/api_service.dart';
import 'package:frontend_flutter/design_system/design_system.dart';

class OperationsScreen extends StatefulWidget {
  const OperationsScreen({super.key, required this.canViewOperations});

  final bool canViewOperations;

  @override
  State<OperationsScreen> createState() => _OperationsScreenState();
}

class _OperationsScreenState extends State<OperationsScreen> {
  WorkerDashboard? _dashboard;
  String? _error;
  Timer? _refreshTimer;

  @override
  void initState() {
    super.initState();
    if (widget.canViewOperations) {
      _load();
      _refreshTimer = Timer.periodic(
        const Duration(seconds: 15),
        (_) => _load(),
      );
    }
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final dashboard = await ApiService.getWorkerDashboard();
      if (!mounted) return;
      setState(() {
        _dashboard = dashboard;
        _error = null;
      });
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.canViewOperations) {
      return const Scaffold(
        body: AppErrorState(
          title: 'Bạn không có quyền truy cập',
          message: 'Bảng vận hành chỉ dành cho quản trị viên AgriMind.',
        ),
      );
    }
    return Scaffold(
      appBar: AppBar(
        title: const Text('Vận hành hệ thống'),
        actions: [
          IconButton(
            onPressed: _load,
            tooltip: 'Làm mới',
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: _dashboard == null && _error == null
          ? const AppLoadingState(message: 'Đang đọc trạng thái worker…')
          : _dashboard == null
          ? AppErrorState(
              title: 'Không tải được trạng thái',
              message: _error!,
              actionLabel: 'Thử lại',
              onAction: _load,
            )
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.symmetric(vertical: AppSpacing.md),
                children: [
                  AppResponsiveContent(child: _DashboardBody(_dashboard!)),
                ],
              ),
            ),
    );
  }
}

class _DashboardBody extends StatelessWidget {
  const _DashboardBody(this.dashboard);

  final WorkerDashboard dashboard;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      AppStatusBanner(
        kind: dashboard.status == 'ok'
            ? AppStatusKind.success
            : AppStatusKind.warning,
        message: dashboard.status == 'ok'
            ? 'Worker đang hoạt động bình thường.'
            : 'Worker đang suy giảm. Hãy kiểm tra chu kỳ lỗi bên dưới.',
      ),
      const SizedBox(height: AppSpacing.lg),
      Text('Chu kỳ worker', style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: AppSpacing.sm),
      ...dashboard.cycles.entries.map(
        (entry) => Padding(
          padding: const EdgeInsets.only(bottom: AppSpacing.sm),
          child: AppCard(
            child: ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Icon(
                entry.value.status == 'ok'
                    ? Icons.check_circle_outline_rounded
                    : Icons.warning_amber_rounded,
              ),
              title: Text(_cycleLabel(entry.key)),
              subtitle: Text(
                'Trạng thái: ${entry.value.status} · cập nhật ${entry.value.ageSeconds ?? '-'} giây trước'
                '${entry.value.errorCode == null ? '' : ' · ${entry.value.errorCode}'}',
              ),
            ),
          ),
        ),
      ),
      const SizedBox(height: AppSpacing.md),
      Text('Gửi thông báo', style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: AppSpacing.sm),
      Wrap(
        spacing: AppSpacing.sm,
        runSpacing: AppSpacing.sm,
        children: dashboard.deliveryCounts.entries
            .map(
              (entry) => Chip(
                label: Text('${_statusLabel(entry.key)}: ${entry.value}'),
              ),
            )
            .toList(),
      ),
      const SizedBox(height: AppSpacing.lg),
      Text('Lần gửi gần đây', style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: AppSpacing.sm),
      if (dashboard.recentAttempts.isEmpty)
        const AppEmptyState(
          title: 'Chưa có lịch sử gửi',
          message: 'Các lần gửi và retry sẽ xuất hiện tại đây.',
        )
      else
        AppCard(
          child: Column(
            children: dashboard.recentAttempts
                .take(10)
                .map(
                  (attempt) => ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(attempt.title),
                    subtitle: Text(
                      'Lần ${attempt.attemptNumber} · ${_statusLabel(attempt.status)}'
                      '${attempt.errorCode == null ? '' : ' · ${attempt.errorCode}'}',
                    ),
                  ),
                )
                .toList(),
          ),
        ),
      const SizedBox(height: AppSpacing.lg),
      Text('Lỗi worker 7 ngày', style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: AppSpacing.sm),
      if (dashboard.recentFailures.isEmpty)
        const AppStatusBanner.success(
          message: 'Không ghi nhận lỗi worker trong 7 ngày gần đây.',
        )
      else
        ...dashboard.recentFailures
            .take(10)
            .map(
              (failure) => Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                child: AppCard(
                  child: ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.error_outline_rounded),
                    title: Text(_cycleLabel(failure.cycle)),
                    subtitle: Text(
                      '${failure.errorCode} · lỗi liên tiếp ${failure.consecutiveFailures}',
                    ),
                  ),
                ),
              ),
            ),
      const SizedBox(height: AppSpacing.xxl),
    ],
  );

  static String _cycleLabel(String value) => switch (value) {
    'task_reminders' => 'Nhắc công việc',
    'farm_monitoring' => 'Theo dõi nông trại',
    'push_deliveries' => 'Gửi thông báo đẩy',
    _ => value,
  };

  static String _statusLabel(String value) => switch (value) {
    'pending' => 'Chờ gửi',
    'retry' => 'Đang thử lại',
    'delivered' => 'Đã gửi',
    'failed' => 'Thất bại',
    'cancelled' => 'Đã hủy',
    _ => value,
  };
}
