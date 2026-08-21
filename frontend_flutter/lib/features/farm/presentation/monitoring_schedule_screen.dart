import 'package:flutter/material.dart';

import 'package:frontend_flutter/data/models/farm_monitoring_schedule.dart';
import 'package:frontend_flutter/data/models/farm_plot.dart';
import 'package:frontend_flutter/data/services/api_service.dart';
import 'package:frontend_flutter/design_system/design_system.dart';

import 'farm_plots_screen.dart';

class MonitoringScheduleScreen extends StatefulWidget {
  const MonitoringScheduleScreen({super.key});

  @override
  State<MonitoringScheduleScreen> createState() =>
      _MonitoringScheduleScreenState();
}

class _MonitoringScheduleScreenState extends State<MonitoringScheduleScreen> {
  late Future<_MonitoringData> _data;
  List<_SeasonOption> _eligibleSeasons = const [];
  String? _selectedSeasonId;
  int _frequencyHours = 24;
  String _notificationScope = 'in_app';
  bool _consent = false;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  void _reload() {
    _data = _loadData();
  }

  Future<_MonitoringData> _loadData() async {
    final schedules = await ApiService.getMonitoringSchedules();
    final plots = await ApiService.getFarmPlots();
    return _MonitoringData(schedules: schedules, plots: plots);
  }

  Future<void> _run(Future<void> Function() action) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await action();
      if (!mounted) return;
      setState(_reload);
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(error.toString().replaceFirst('Exception: ', '')),
        ),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _create() => _run(() async {
    if (!_consent || _eligibleSeasons.isEmpty) return;
    final seasonId = _selectedSeasonId ?? _eligibleSeasons.first.season.id;
    await ApiService.createMonitoringSchedule(
      cropSeasonId: seasonId,
      frequencyHours: _frequencyHours,
      notificationScope: _notificationScope,
    );
    if (mounted) {
      setState(() {
        _consent = false;
        _selectedSeasonId = null;
      });
    }
  });

  Future<void> _update(
    FarmMonitoringSchedule schedule,
    Map<String, dynamic> changes,
  ) => _run(() async {
    await ApiService.updateMonitoringSchedule(schedule.id, changes);
  });

  Future<void> _delete(FarmMonitoringSchedule schedule) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Xóa lịch theo dõi?'),
        content: const Text(
          'Lịch sẽ ngừng chạy. Dữ liệu dự báo cũ vẫn được giữ để kiểm tra lịch sử.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Giữ lại'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Xóa lịch'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    await _run(() => ApiService.deleteMonitoringSchedule(schedule.id));
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Theo dõi cây trồng')),
    body: FutureBuilder<_MonitoringData>(
      future: _data,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return _ErrorState(onRetry: () => setState(_reload));
        }
        final data = snapshot.data ?? const _MonitoringData();
        final schedules = data.schedules;
        final usedSeasons = schedules
            .map((item) => item.cropSeasonId)
            .whereType<String>()
            .toSet();
        _eligibleSeasons = [
          for (final plot in data.plots)
            for (final season in plot.seasons)
              if (season.isActive && !usedSeasons.contains(season.id))
                _SeasonOption(plot: plot, season: season),
        ];
        final plotNames = {for (final plot in data.plots) plot.id: plot.name};
        return ListView(
          padding: const EdgeInsets.fromLTRB(18, 12, 18, 32),
          children: [
            const _ScopeNotice(),
            const SizedBox(height: AppSpacing.md),
            ...schedules.map(
              (item) => _buildScheduleCard(
                item,
                plotNames[item.plotId] ?? 'Thửa chưa xác định',
              ),
            ),
            if (_eligibleSeasons.isNotEmpty) ...[
              if (schedules.isNotEmpty) const SizedBox(height: 2),
              _buildCreateCard(_eligibleSeasons),
            ] else if (schedules.isEmpty)
              _buildMissingSeasonCard(),
          ],
        );
      },
    ),
  );

  Widget _buildCreateCard(List<_SeasonOption> options) {
    final selected = options.any((item) => item.season.id == _selectedSeasonId)
        ? _selectedSeasonId
        : options.first.season.id;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Bật cảnh báo nguy cơ',
              style: Theme.of(
                context,
              ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: AppSpacing.xs),
            const Text(
              'Chọn mùa vụ đang hoạt động để cảnh báo thời tiết gắn với đúng cây và thửa đất.',
              style: TextStyle(color: AppColors.muted, height: 1.4),
            ),
            const SizedBox(height: 18),
            DropdownButtonFormField<String>(
              initialValue: selected,
              decoration: const InputDecoration(labelText: 'Mùa vụ theo dõi'),
              items: [
                for (final option in options)
                  DropdownMenuItem(
                    value: option.season.id,
                    child: Text('${option.plot.name} · ${option.season.crop}'),
                  ),
              ],
              onChanged: (value) => setState(() => _selectedSeasonId = value),
            ),
            const SizedBox(height: AppSpacing.sm),
            _frequencyField(_frequencyHours, (value) {
              if (value != null) setState(() => _frequencyHours = value);
            }),
            const SizedBox(height: AppSpacing.sm),
            _scopeField(_notificationScope, (value) {
              if (value != null) setState(() => _notificationScope = value);
            }),
            const SizedBox(height: 10),
            CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              value: _consent,
              onChanged: (value) => setState(() => _consent = value ?? false),
              title: const Text(
                'Tôi đồng ý cho AgriMind kiểm tra thời tiết theo lịch',
              ),
              subtitle: const Text(
                'Có thể tạm dừng hoặc xóa lịch bất cứ lúc nào.',
              ),
              controlAffinity: ListTileControlAffinity.leading,
            ),
            const SizedBox(height: AppSpacing.xs),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: _busy || !_consent ? null : _create,
                icon: const Icon(Icons.add_alert_outlined),
                label: const Text('Bật theo dõi'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildMissingSeasonCard() => Card(
    child: Padding(
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Cần một mùa vụ đang hoạt động',
            style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16),
          ),
          const SizedBox(height: AppSpacing.xs),
          const Text(
            'Hãy tạo thửa đất và bắt đầu mùa vụ trước khi bật lịch theo dõi.',
            style: TextStyle(color: AppColors.muted, height: 1.4),
          ),
          const SizedBox(height: 14),
          FilledButton.icon(
            onPressed: () async {
              await Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const FarmPlotsScreen()),
              );
              if (mounted) setState(_reload);
            },
            icon: const Icon(Icons.landscape_outlined),
            label: const Text('Quản lý thửa và mùa vụ'),
          ),
        ],
      ),
    ),
  );

  Widget _buildScheduleCard(FarmMonitoringSchedule schedule, String plotName) {
    final prediction = schedule.latestPrediction;
    return Card(
      margin: const EdgeInsets.only(bottom: 14),
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  schedule.isActive
                      ? Icons.sensors
                      : Icons.pause_circle_outline,
                  color: schedule.isActive ? AppColors.forest : AppColors.muted,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    '$plotName · ${schedule.crop}',
                    style: const TextStyle(
                      fontWeight: FontWeight.w800,
                      fontSize: 16,
                    ),
                  ),
                ),
                _StatusChip(active: schedule.isActive),
              ],
            ),
            const SizedBox(height: 18),
            _frequencyField(
              schedule.frequencyHours,
              _busy
                  ? null
                  : (value) {
                      if (value != null) {
                        _update(schedule, {'frequency_hours': value});
                      }
                    },
            ),
            const SizedBox(height: AppSpacing.sm),
            _scopeField(
              schedule.notificationScope,
              _busy
                  ? null
                  : (value) {
                      if (value != null) {
                        _update(schedule, {'notification_scope': value});
                      }
                    },
            ),
            const SizedBox(height: 18),
            if (prediction == null)
              const Text(
                'Chưa có lần đánh giá nào. Worker sẽ chạy khi đến lịch.',
                style: TextStyle(color: AppColors.muted),
              )
            else
              _PredictionPanel(prediction: prediction),
            if (schedule.lastErrorCode != null) ...[
              const SizedBox(height: AppSpacing.sm),
              const Text(
                'Lần kiểm tra gần nhất chưa lấy được thời tiết; hệ thống sẽ tự thử lại.',
                style: TextStyle(color: AppColors.warning),
              ),
            ],
            const SizedBox(height: 18),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _busy
                        ? null
                        : () => _update(schedule, {
                            'status': schedule.isActive ? 'paused' : 'active',
                          }),
                    icon: Icon(
                      schedule.isActive ? Icons.pause : Icons.play_arrow,
                    ),
                    label: Text(schedule.isActive ? 'Tạm dừng' : 'Tiếp tục'),
                  ),
                ),
                const SizedBox(width: 10),
                IconButton(
                  tooltip: 'Xóa lịch',
                  onPressed: _busy ? null : () => _delete(schedule),
                  icon: const Icon(Icons.delete_outline),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  DropdownButtonFormField<int> _frequencyField(
    int value,
    ValueChanged<int?>? onChanged,
  ) => DropdownButtonFormField<int>(
    initialValue: value,
    decoration: const InputDecoration(labelText: 'Tần suất kiểm tra'),
    items: const [
      DropdownMenuItem(value: 6, child: Text('Mỗi 6 giờ')),
      DropdownMenuItem(value: 12, child: Text('Mỗi 12 giờ')),
      DropdownMenuItem(value: 24, child: Text('Mỗi 24 giờ')),
    ],
    onChanged: onChanged,
  );

  DropdownButtonFormField<String> _scopeField(
    String value,
    ValueChanged<String?>? onChanged,
  ) => DropdownButtonFormField<String>(
    initialValue: value,
    decoration: const InputDecoration(labelText: 'Kênh thông báo'),
    items: const [
      DropdownMenuItem(value: 'in_app', child: Text('Chỉ trong ứng dụng')),
      DropdownMenuItem(
        value: 'push_and_in_app',
        child: Text('Ứng dụng và thông báo đẩy'),
      ),
    ],
    onChanged: onChanged,
  );
}

class _ScopeNotice extends StatelessWidget {
  const _ScopeNotice();

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(
      color: AppColors.mint,
      borderRadius: BorderRadius.circular(AppRadius.input),
    ),
    child: const Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(Icons.science_outlined, color: AppColors.forest),
        SizedBox(width: 12),
        Expanded(
          child: Text(
            'Theo dõi đã hỗ trợ mọi tỉnh và mọi cây trồng. Các cây phổ biến dùng policy riêng; cây khác dùng cảnh báo thời tiết an toàn. Kết quả không thay thế kiểm tra hoặc chẩn đoán tại ruộng.',
            style: TextStyle(color: AppColors.ink, height: 1.4),
          ),
        ),
      ],
    ),
  );
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.active});
  final bool active;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
    decoration: BoxDecoration(
      color: active ? AppColors.mint : AppColors.surfaceDisabled,
      borderRadius: BorderRadius.circular(20),
    ),
    child: Text(
      active ? 'Đang chạy' : 'Tạm dừng',
      style: TextStyle(
        color: active ? AppColors.forest : AppColors.muted,
        fontSize: 12,
        fontWeight: FontWeight.w700,
      ),
    ),
  );
}

class _PredictionPanel extends StatelessWidget {
  const _PredictionPanel({required this.prediction});
  final FarmRiskPrediction prediction;

  @override
  Widget build(BuildContext context) {
    final labels = {'low': 'Thấp', 'medium': 'Trung bình', 'high': 'Cao'};
    final categoryLabels = {
      'leafy_vegetable': 'Rau ăn lá',
      'brassica_vegetable': 'Rau họ cải',
      'stem_flower_vegetable': 'Rau ăn thân/hoa',
      'fruiting_vegetable': 'Rau ăn quả',
      'cucurbit_vegetable': 'Dưa và bí',
      'legume_vegetable': 'Rau họ đậu',
      'root_vegetable': 'Rau ăn củ',
      'tuber_vegetable': 'Củ lấy tinh bột',
      'allium_vegetable': 'Hành và tỏi',
      'herb_vegetable': 'Rau gia vị',
      'rhizome_vegetable': 'Thân rễ',
    };
    final category = prediction.inputs['policy_category']?.toString();
    final categoryLabel = categoryLabels[category];
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.warningSurface,
        borderRadius: BorderRadius.circular(AppRadius.input),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Nguy cơ gần nhất: ${labels[prediction.riskLevel] ?? prediction.riskLevel}',
            style: const TextStyle(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 5),
          Text(
            'Độ tin cậy chính sách: ${(prediction.confidence * 100).round()}% · ${prediction.policyVersion}',
            style: const TextStyle(color: AppColors.muted, fontSize: 12),
          ),
          if (categoryLabel != null) ...[
            const SizedBox(height: 4),
            Text(
              'Nhóm theo dõi: $categoryLabel',
              style: const TextStyle(color: AppColors.muted, fontSize: 12),
            ),
          ],
        ],
      ),
    );
  }
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.onRetry});
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Center(
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Icon(Icons.cloud_off_outlined, size: 48, color: AppColors.muted),
        const SizedBox(height: AppSpacing.sm),
        const Text('Chưa tải được lịch theo dõi.'),
        const SizedBox(height: AppSpacing.xs),
        TextButton(onPressed: onRetry, child: const Text('Thử lại')),
      ],
    ),
  );
}

class _MonitoringData {
  const _MonitoringData({this.schedules = const [], this.plots = const []});

  final List<FarmMonitoringSchedule> schedules;
  final List<FarmPlot> plots;
}

class _SeasonOption {
  const _SeasonOption({required this.plot, required this.season});

  final FarmPlot plot;
  final CropSeason season;
}
