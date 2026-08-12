import 'package:flutter/material.dart';

import '../models/farm_plot.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';

class FarmPlotsScreen extends StatefulWidget {
  const FarmPlotsScreen({super.key});

  @override
  State<FarmPlotsScreen> createState() => _FarmPlotsScreenState();
}

class _FarmPlotsScreenState extends State<FarmPlotsScreen> {
  late Future<List<FarmPlot>> _plots;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  void _reload() => _plots = ApiService.getFarmPlots();

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

  Future<void> _createPlot() async {
    final name = TextEditingController();
    final area = TextEditingController();
    final note = TextEditingController();
    final accepted = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Thêm thửa đất'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: name,
                autofocus: true,
                decoration: const InputDecoration(labelText: 'Tên thửa *'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: area,
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                ),
                decoration: const InputDecoration(labelText: 'Diện tích (ha)'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: note,
                decoration: const InputDecoration(
                  labelText: 'Vị trí / ghi chú',
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Hủy'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Tạo thửa'),
          ),
        ],
      ),
    );
    final plotName = name.text.trim();
    final areaText = area.text.trim().replaceAll(',', '.');
    final areaValue = double.tryParse(areaText);
    final noteValue = note.text.trim();
    name.dispose();
    area.dispose();
    note.dispose();
    if (accepted != true || plotName.isEmpty) return;
    if (areaText.isNotEmpty && areaValue == null) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Diện tích cần là một con số hợp lệ.')),
        );
      }
      return;
    }
    await _run(
      () async => ApiService.createFarmPlot(
        name: plotName,
        areaHa: areaValue,
        locationNote: noteValue.isEmpty ? null : noteValue,
      ),
    );
  }

  Future<void> _createSeason(FarmPlot plot) async {
    final crop = TextEditingController();
    final variety = TextEditingController();
    final stage = TextEditingController();
    DateTime? plantedOn;
    DateTime? expectedHarvestOn;
    final accepted = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text('Mùa vụ mới · ${plot.name}'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: crop,
                  autofocus: true,
                  decoration: const InputDecoration(
                    labelText: 'Cây trồng *',
                    hintText: 'Ví dụ: Cà chua',
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: variety,
                  decoration: const InputDecoration(labelText: 'Giống'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: stage,
                  decoration: const InputDecoration(
                    labelText: 'Giai đoạn hiện tại',
                  ),
                ),
                const SizedBox(height: 12),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.event_outlined),
                  title: Text(
                    plantedOn == null
                        ? 'Chọn ngày trồng'
                        : '${plantedOn!.day}/${plantedOn!.month}/${plantedOn!.year}',
                  ),
                  onTap: () async {
                    final selected = await showDatePicker(
                      context: dialogContext,
                      initialDate: plantedOn ?? DateTime.now(),
                      firstDate: DateTime(2020),
                      lastDate: DateTime(2035),
                    );
                    if (selected != null) {
                      setDialogState(() => plantedOn = selected);
                    }
                  },
                ),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.event_available_outlined),
                  title: Text(
                    expectedHarvestOn == null
                        ? 'Chọn ngày dự kiến thu hoạch'
                        : '${expectedHarvestOn!.day}/${expectedHarvestOn!.month}/${expectedHarvestOn!.year}',
                  ),
                  onTap: () async {
                    final selected = await showDatePicker(
                      context: dialogContext,
                      initialDate:
                          expectedHarvestOn ??
                          plantedOn?.add(const Duration(days: 90)) ??
                          DateTime.now().add(const Duration(days: 90)),
                      firstDate: plantedOn ?? DateTime(2020),
                      lastDate: DateTime(2035),
                    );
                    if (selected != null) {
                      setDialogState(() => expectedHarvestOn = selected);
                    }
                  },
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Hủy'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Bắt đầu mùa vụ'),
            ),
          ],
        ),
      ),
    );
    final cropValue = crop.text.trim();
    final varietyValue = variety.text.trim();
    final stageValue = stage.text.trim();
    crop.dispose();
    variety.dispose();
    stage.dispose();
    if (accepted != true || cropValue.isEmpty) return;
    await _run(
      () async => ApiService.createCropSeason(
        plotId: plot.id,
        crop: cropValue,
        variety: varietyValue.isEmpty ? null : varietyValue,
        growthStage: stageValue.isEmpty ? null : stageValue,
        plantedOn: plantedOn,
        expectedHarvestOn: expectedHarvestOn,
      ),
    );
  }

  Future<void> _completeSeason(CropSeason season) async {
    final accepted = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Kết thúc mùa vụ?'),
        content: const Text(
          'Lịch theo dõi đang chạy cho mùa vụ này sẽ tự động tạm dừng.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Chưa kết thúc'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Kết thúc'),
          ),
        ],
      ),
    );
    if (accepted != true) return;
    await _run(
      () async =>
          ApiService.updateCropSeason(season.id, {'status': 'completed'}),
    );
  }

  Future<void> _archivePlot(FarmPlot plot) async {
    final accepted = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Lưu trữ thửa đất?'),
        content: const Text(
          'Chỉ có thể lưu trữ khi thửa không còn mùa vụ active hoặc lịch theo dõi.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Hủy'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Lưu trữ'),
          ),
        ],
      ),
    );
    if (accepted != true) return;
    await _run(() => ApiService.archiveFarmPlot(plot.id));
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('Thửa đất và mùa vụ'),
      actions: [
        IconButton(
          tooltip: 'Thêm thửa',
          onPressed: _busy ? null : _createPlot,
          icon: const Icon(Icons.add_rounded),
        ),
      ],
    ),
    body: FutureBuilder<List<FarmPlot>>(
      future: _plots,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return _EmptyState(
            message: 'Chưa tải được danh sách thửa đất.',
            actionLabel: 'Thử lại',
            onAction: () => setState(_reload),
          );
        }
        final plots = snapshot.data ?? const [];
        if (plots.isEmpty) {
          return _EmptyState(
            message: 'Tạo thửa đất đầu tiên để quản lý mùa vụ riêng biệt.',
            actionLabel: 'Thêm thửa đất',
            onAction: _createPlot,
          );
        }
        return ListView.builder(
          padding: const EdgeInsets.fromLTRB(18, 12, 18, 32),
          itemCount: plots.length,
          itemBuilder: (context, index) => _plotCard(plots[index]),
        );
      },
    ),
  );

  Widget _plotCard(FarmPlot plot) {
    final active = plot.activeSeason;
    return Card(
      margin: const EdgeInsets.only(bottom: 14),
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.landscape_outlined, color: AppColors.forest),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    plot.name,
                    style: const TextStyle(
                      fontSize: 17,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
                IconButton(
                  tooltip: 'Lưu trữ thửa',
                  onPressed: _busy ? null : () => _archivePlot(plot),
                  icon: const Icon(Icons.archive_outlined),
                ),
              ],
            ),
            if (plot.areaHa != null || plot.locationNote != null) ...[
              const SizedBox(height: 6),
              Text(
                [
                  if (plot.areaHa != null) '${plot.areaHa} ha',
                  if (plot.locationNote != null) plot.locationNote!,
                ].join(' · '),
                style: const TextStyle(color: AppColors.muted),
              ),
            ],
            const SizedBox(height: 16),
            if (active == null)
              const Text(
                'Chưa có mùa vụ đang hoạt động.',
                style: TextStyle(color: AppColors.muted),
              )
            else
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: AppColors.mint,
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      active.crop,
                      style: const TextStyle(fontWeight: FontWeight.w800),
                    ),
                    if (active.variety != null || active.growthStage != null)
                      Text(
                        [
                          if (active.variety != null) 'Giống ${active.variety}',
                          if (active.growthStage != null) active.growthStage!,
                        ].join(' · '),
                        style: const TextStyle(color: AppColors.muted),
                      ),
                  ],
                ),
              ),
            const SizedBox(height: 14),
            Row(
              children: [
                if (active == null)
                  Expanded(
                    child: FilledButton.icon(
                      onPressed: _busy ? null : () => _createSeason(plot),
                      icon: const Icon(Icons.eco_outlined),
                      label: const Text('Bắt đầu mùa vụ'),
                    ),
                  )
                else
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: _busy ? null : () => _completeSeason(active),
                      icon: const Icon(Icons.flag_outlined),
                      label: const Text('Kết thúc mùa vụ'),
                    ),
                  ),
              ],
            ),
            if (plot.seasons.where((item) => !item.isActive).isNotEmpty) ...[
              const SizedBox(height: 14),
              Text(
                'Lịch sử: ${plot.seasons.where((item) => !item.isActive).map((item) => item.crop).take(3).join(', ')}',
                style: const TextStyle(color: AppColors.muted, fontSize: 12),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({
    required this.message,
    required this.actionLabel,
    required this.onAction,
  });

  final String message;
  final String actionLabel;
  final VoidCallback onAction;

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(28),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(
            Icons.landscape_outlined,
            size: 54,
            color: AppColors.muted,
          ),
          const SizedBox(height: 14),
          Text(message, textAlign: TextAlign.center),
          const SizedBox(height: 12),
          FilledButton(onPressed: onAction, child: Text(actionLabel)),
        ],
      ),
    ),
  );
}
