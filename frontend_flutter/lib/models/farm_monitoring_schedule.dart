class FarmRiskPrediction {
  const FarmRiskPrediction({
    required this.riskType,
    required this.riskLevel,
    required this.confidence,
    required this.policyVersion,
    required this.inputs,
    required this.expiresAt,
    required this.createdAt,
  });

  final String riskType;
  final String riskLevel;
  final double confidence;
  final String policyVersion;
  final Map<String, dynamic> inputs;
  final DateTime? expiresAt;
  final DateTime? createdAt;

  factory FarmRiskPrediction.fromJson(Map<String, dynamic> json) =>
      FarmRiskPrediction(
        riskType: json['risk_type']?.toString() ?? '',
        riskLevel: json['risk_level']?.toString() ?? 'unknown',
        confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
        policyVersion: json['policy_version']?.toString() ?? '',
        inputs: Map<String, dynamic>.from(
          json['inputs'] as Map? ?? const <String, dynamic>{},
        ),
        expiresAt: DateTime.tryParse(json['expires_at']?.toString() ?? ''),
        createdAt: DateTime.tryParse(json['created_at']?.toString() ?? ''),
      );
}

class FarmMonitoringSchedule {
  const FarmMonitoringSchedule({
    required this.id,
    required this.crop,
    required this.province,
    required this.reminderType,
    required this.frequencyHours,
    required this.notificationScope,
    required this.status,
    this.plotId,
    this.cropSeasonId,
    this.nextRunAt,
    this.lastRunAt,
    this.lastErrorCode,
    this.latestPrediction,
  });

  final String id;
  final String crop;
  final String province;
  final String reminderType;
  final int frequencyHours;
  final String notificationScope;
  final String status;
  final String? plotId;
  final String? cropSeasonId;
  final DateTime? nextRunAt;
  final DateTime? lastRunAt;
  final String? lastErrorCode;
  final FarmRiskPrediction? latestPrediction;

  bool get isActive => status == 'active';

  factory FarmMonitoringSchedule.fromJson(Map<String, dynamic> json) {
    final prediction = json['latest_prediction'];
    return FarmMonitoringSchedule(
      id: json['id']?.toString() ?? '',
      crop: json['crop']?.toString() ?? '',
      province: json['province']?.toString() ?? '',
      reminderType: json['reminder_type']?.toString() ?? '',
      frequencyHours: (json['frequency_hours'] as num?)?.toInt() ?? 24,
      notificationScope: json['notification_scope']?.toString() ?? 'in_app',
      status: json['status']?.toString() ?? 'paused',
      plotId: json['plot_id']?.toString(),
      cropSeasonId: json['crop_season_id']?.toString(),
      nextRunAt: DateTime.tryParse(json['next_run_at']?.toString() ?? ''),
      lastRunAt: DateTime.tryParse(json['last_run_at']?.toString() ?? ''),
      lastErrorCode: json['last_error_code']?.toString(),
      latestPrediction: prediction is Map<String, dynamic>
          ? FarmRiskPrediction.fromJson(prediction)
          : null,
    );
  }
}
