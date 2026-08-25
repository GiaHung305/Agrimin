class WorkerDashboard {
  const WorkerDashboard({
    required this.status,
    required this.cycles,
    required this.deliveryCounts,
    required this.recentAttempts,
    required this.recentFailures,
    required this.checkedAt,
  });

  final String status;
  final Map<String, WorkerCycleStatus> cycles;
  final Map<String, int> deliveryCounts;
  final List<DeliveryAttemptItem> recentAttempts;
  final List<WorkerFailureItem> recentFailures;
  final DateTime? checkedAt;

  factory WorkerDashboard.fromJson(Map<String, dynamic> json) {
    final worker = json['worker'] as Map<String, dynamic>? ?? const {};
    final deliveries = json['deliveries'] as Map<String, dynamic>? ?? const {};
    final cycleJson = worker['cycles'] as Map<String, dynamic>? ?? const {};
    final countJson = deliveries['counts'] as Map<String, dynamic>? ?? const {};
    return WorkerDashboard(
      status: worker['status']?.toString() ?? 'degraded',
      cycles: cycleJson.map(
        (key, value) => MapEntry(
          key,
          WorkerCycleStatus.fromJson(value as Map<String, dynamic>),
        ),
      ),
      deliveryCounts: countJson.map(
        (key, value) => MapEntry(key, (value as num?)?.toInt() ?? 0),
      ),
      recentAttempts:
          (deliveries['recent_attempts'] as List<dynamic>? ?? const [])
              .map(
                (value) =>
                    DeliveryAttemptItem.fromJson(value as Map<String, dynamic>),
              )
              .toList(),
      recentFailures: (json['recent_failures'] as List<dynamic>? ?? const [])
          .map(
            (value) =>
                WorkerFailureItem.fromJson(value as Map<String, dynamic>),
          )
          .toList(),
      checkedAt: DateTime.tryParse(json['checked_at']?.toString() ?? ''),
    );
  }
}

class WorkerCycleStatus {
  const WorkerCycleStatus({
    required this.status,
    required this.ageSeconds,
    required this.consecutiveFailures,
    this.errorCode,
  });

  final String status;
  final int? ageSeconds;
  final int consecutiveFailures;
  final String? errorCode;

  factory WorkerCycleStatus.fromJson(Map<String, dynamic> json) =>
      WorkerCycleStatus(
        status: json['status']?.toString() ?? 'unknown',
        ageSeconds: (json['age_seconds'] as num?)?.toInt(),
        consecutiveFailures:
            (json['consecutive_failures'] as num?)?.toInt() ?? 0,
        errorCode: json['error_code']?.toString(),
      );
}

class DeliveryAttemptItem {
  const DeliveryAttemptItem({
    required this.title,
    required this.attemptNumber,
    required this.status,
    required this.createdAt,
    this.errorCode,
  });

  final String title;
  final int attemptNumber;
  final String status;
  final DateTime? createdAt;
  final String? errorCode;

  factory DeliveryAttemptItem.fromJson(Map<String, dynamic> json) =>
      DeliveryAttemptItem(
        title: json['notification_title']?.toString() ?? 'Thông báo',
        attemptNumber: (json['attempt_number'] as num?)?.toInt() ?? 0,
        status: json['status']?.toString() ?? 'unknown',
        createdAt: DateTime.tryParse(json['created_at']?.toString() ?? ''),
        errorCode: json['error_code']?.toString(),
      );
}

class WorkerFailureItem {
  const WorkerFailureItem({
    required this.cycle,
    required this.errorCode,
    required this.consecutiveFailures,
    required this.createdAt,
  });

  final String cycle;
  final String errorCode;
  final int consecutiveFailures;
  final DateTime? createdAt;

  factory WorkerFailureItem.fromJson(Map<String, dynamic> json) =>
      WorkerFailureItem(
        cycle: json['cycle']?.toString() ?? 'unknown',
        errorCode: json['error_code']?.toString() ?? 'unknown',
        consecutiveFailures:
            (json['consecutive_failures'] as num?)?.toInt() ?? 0,
        createdAt: DateTime.tryParse(json['created_at']?.toString() ?? ''),
      );
}
