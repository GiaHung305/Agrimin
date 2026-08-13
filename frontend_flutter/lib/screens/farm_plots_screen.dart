import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';

import '../models/farm_plot.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';

class FarmPlotsScreen extends StatefulWidget {
  const FarmPlotsScreen({super.key});

  @override
  State<FarmPlotsScreen> createState() => _FarmPlotsScreenState();
}

class _FarmPlotsScreenState extends State<FarmPlotsScreen> {
  static const _growthStageOptions = <String>[
    'Khởi đầu / cây con',
    'Sinh trưởng',
    'Giữa vụ / sinh sản',
    'Cuối vụ / chín',
  ];

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
    final latitude = TextEditingController();
    final longitude = TextEditingController();
    Position? capturedPosition;
    bool locating = false;
    String? locationError;
    final accepted = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
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
                  decoration: const InputDecoration(
                    labelText: 'Diện tích (ha)',
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: note,
                  decoration: const InputDecoration(
                    labelText: 'Vị trí / ghi chú',
                  ),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: latitude,
                        keyboardType: const TextInputType.numberWithOptions(
                          decimal: true,
                          signed: true,
                        ),
                        decoration: const InputDecoration(labelText: 'Vĩ độ'),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: TextField(
                        controller: longitude,
                        keyboardType: const TextInputType.numberWithOptions(
                          decimal: true,
                          signed: true,
                        ),
                        decoration: const InputDecoration(labelText: 'Kinh độ'),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton.icon(
                    onPressed: locating
                        ? null
                        : () async {
                            setDialogState(() {
                              locating = true;
                              locationError = null;
                            });
                            try {
                              final position = await _getCurrentPosition();
                              if (!dialogContext.mounted) return;
                              latitude.text = position.latitude.toStringAsFixed(
                                6,
                              );
                              longitude.text = position.longitude
                                  .toStringAsFixed(6);
                              setDialogState(() => capturedPosition = position);
                            } catch (error) {
                              if (!dialogContext.mounted) return;
                              setDialogState(
                                () => locationError = error
                                    .toString()
                                    .replaceFirst('Exception: ', ''),
                              );
                            } finally {
                              if (dialogContext.mounted) {
                                setDialogState(() => locating = false);
                              }
                            }
                          },
                    icon: locating
                        ? const SizedBox.square(
                            dimension: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.my_location),
                    label: Text(
                      locating ? 'Đang lấy vị trí…' : 'Lấy GPS hiện tại',
                    ),
                  ),
                ),
                if (locationError != null) ...[
                  const SizedBox(height: 6),
                  Text(
                    locationError!,
                    style: const TextStyle(color: Colors.red, fontSize: 12),
                  ),
                ],
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Hủy'),
            ),
            FilledButton(
              onPressed: locating ? null : () => Navigator.pop(context, true),
              child: const Text('Tạo thửa'),
            ),
          ],
        ),
      ),
    );
    final plotName = name.text.trim();
    final areaText = area.text.trim().replaceAll(',', '.');
    final areaValue = double.tryParse(areaText);
    final noteValue = note.text.trim();
    final latitudeText = latitude.text.trim().replaceAll(',', '.');
    final longitudeText = longitude.text.trim().replaceAll(',', '.');
    final latitudeValue = double.tryParse(latitudeText);
    final longitudeValue = double.tryParse(longitudeText);
    final deviceCoordinatesUnchanged =
        capturedPosition != null &&
        latitudeText == capturedPosition!.latitude.toStringAsFixed(6) &&
        longitudeText == capturedPosition!.longitude.toStringAsFixed(6);
    name.dispose();
    area.dispose();
    note.dispose();
    latitude.dispose();
    longitude.dispose();
    if (accepted != true || plotName.isEmpty) return;
    if (areaText.isNotEmpty && areaValue == null) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Diện tích cần là một con số hợp lệ.')),
        );
      }
      return;
    }
    if ((latitudeText.isEmpty) != (longitudeText.isEmpty) ||
        (latitudeText.isNotEmpty &&
            (latitudeValue == null || longitudeValue == null))) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Vĩ độ và kinh độ phải là hai số hợp lệ.'),
          ),
        );
      }
      return;
    }
    await _run(
      () async => ApiService.createFarmPlot(
        name: plotName,
        areaHa: areaValue,
        locationNote: noteValue.isEmpty ? null : noteValue,
        latitude: latitudeValue,
        longitude: longitudeValue,
        elevationM: deviceCoordinatesUnchanged
            ? capturedPosition!.altitude
            : null,
        locationAccuracyM: deviceCoordinatesUnchanged
            ? capturedPosition!.accuracy
            : null,
        locationSource: latitudeValue == null
            ? null
            : deviceCoordinatesUnchanged
            ? 'device'
            : 'manual',
      ),
    );
  }

  Future<Position> _getCurrentPosition() async {
    if (!await Geolocator.isLocationServiceEnabled()) {
      throw Exception('Dịch vụ vị trí đang tắt trên thiết bị.');
    }
    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    if (permission == LocationPermission.denied) {
      throw Exception('Bạn chưa cấp quyền vị trí cho AgriMind.');
    }
    if (permission == LocationPermission.deniedForever) {
      throw Exception(
        'Quyền vị trí đã bị chặn. Hãy mở cài đặt ứng dụng để cấp lại.',
      );
    }
    return Geolocator.getCurrentPosition(
      locationSettings: const LocationSettings(
        accuracy: LocationAccuracy.high,
        timeLimit: Duration(seconds: 15),
      ),
    );
  }

  Future<void> _editPlotLocation(FarmPlot plot) async {
    final latitude = TextEditingController(
      text: plot.latitude?.toStringAsFixed(6) ?? '',
    );
    final longitude = TextEditingController(
      text: plot.longitude?.toStringAsFixed(6) ?? '',
    );
    Position? capturedPosition;
    bool locating = false;
    String? locationError;
    final accepted = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text('GPS · ${plot.name}'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: latitude,
                        keyboardType: const TextInputType.numberWithOptions(
                          decimal: true,
                          signed: true,
                        ),
                        decoration: const InputDecoration(labelText: 'Vĩ độ'),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: TextField(
                        controller: longitude,
                        keyboardType: const TextInputType.numberWithOptions(
                          decimal: true,
                          signed: true,
                        ),
                        decoration: const InputDecoration(labelText: 'Kinh độ'),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton.icon(
                    onPressed: locating
                        ? null
                        : () async {
                            setDialogState(() {
                              locating = true;
                              locationError = null;
                            });
                            try {
                              final position = await _getCurrentPosition();
                              if (!dialogContext.mounted) return;
                              latitude.text = position.latitude.toStringAsFixed(
                                6,
                              );
                              longitude.text = position.longitude
                                  .toStringAsFixed(6);
                              setDialogState(() => capturedPosition = position);
                            } catch (error) {
                              if (!dialogContext.mounted) return;
                              setDialogState(
                                () => locationError = error
                                    .toString()
                                    .replaceFirst('Exception: ', ''),
                              );
                            } finally {
                              if (dialogContext.mounted) {
                                setDialogState(() => locating = false);
                              }
                            }
                          },
                    icon: locating
                        ? const SizedBox.square(
                            dimension: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.my_location),
                    label: Text(
                      locating
                          ? 'Đang lấy vị trí…'
                          : 'Cập nhật từ GPS thiết bị',
                    ),
                  ),
                ),
                if (locationError != null) ...[
                  const SizedBox(height: 6),
                  Text(
                    locationError!,
                    style: const TextStyle(color: Colors.red, fontSize: 12),
                  ),
                ],
                const SizedBox(height: 8),
                const Text(
                  'Tọa độ chỉ được lấy khi bạn bấm nút và dùng cho dự báo thời tiết của thửa này.',
                  style: TextStyle(color: AppColors.muted, fontSize: 12),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: locating
                  ? null
                  : () {
                      latitude.clear();
                      longitude.clear();
                      capturedPosition = null;
                      setDialogState(() => locationError = null);
                    },
              child: const Text('Xóa GPS'),
            ),
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Hủy'),
            ),
            FilledButton(
              onPressed: locating ? null : () => Navigator.pop(context, true),
              child: const Text('Lưu'),
            ),
          ],
        ),
      ),
    );
    final latitudeText = latitude.text.trim().replaceAll(',', '.');
    final longitudeText = longitude.text.trim().replaceAll(',', '.');
    final latitudeValue = double.tryParse(latitudeText);
    final longitudeValue = double.tryParse(longitudeText);
    final originalUnchanged =
        capturedPosition == null &&
        latitudeText == (plot.latitude?.toStringAsFixed(6) ?? '') &&
        longitudeText == (plot.longitude?.toStringAsFixed(6) ?? '');
    final capturedUnchanged =
        capturedPosition != null &&
        latitudeText == capturedPosition!.latitude.toStringAsFixed(6) &&
        longitudeText == capturedPosition!.longitude.toStringAsFixed(6);
    latitude.dispose();
    longitude.dispose();
    if (accepted != true) return;
    if ((latitudeText.isEmpty) != (longitudeText.isEmpty) ||
        (latitudeText.isNotEmpty &&
            (latitudeValue == null || longitudeValue == null))) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Vĩ độ và kinh độ phải là hai số hợp lệ.'),
          ),
        );
      }
      return;
    }
    await _run(
      () => ApiService.updateFarmPlot(plot.id, {
        'latitude': latitudeValue,
        'longitude': longitudeValue,
        'elevation_m': capturedUnchanged
            ? capturedPosition!.altitude
            : originalUnchanged
            ? plot.elevationM
            : null,
        'location_accuracy_m': capturedUnchanged
            ? capturedPosition!.accuracy
            : originalUnchanged
            ? plot.locationAccuracyM
            : null,
        'location_source': latitudeValue == null
            ? null
            : capturedUnchanged
            ? 'device'
            : originalUnchanged
            ? plot.locationSource ?? 'manual'
            : 'manual',
      }),
    );
  }

  Future<void> _createSeason(FarmPlot plot) async {
    final crop = TextEditingController();
    final variety = TextEditingController();
    String? stageValue;
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
                DropdownButtonFormField<String>(
                  initialValue: stageValue,
                  decoration: const InputDecoration(
                    labelText: 'Giai đoạn hiện tại',
                  ),
                  items: _growthStageOptions
                      .map(
                        (stage) =>
                            DropdownMenuItem(value: stage, child: Text(stage)),
                      )
                      .toList(),
                  onChanged: (value) =>
                      setDialogState(() => stageValue = value),
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
    crop.dispose();
    variety.dispose();
    if (accepted != true || cropValue.isEmpty) return;
    await _run(
      () async => ApiService.createCropSeason(
        plotId: plot.id,
        crop: cropValue,
        variety: varietyValue.isEmpty ? null : varietyValue,
        growthStage: stageValue,
        plantedOn: plantedOn,
        expectedHarvestOn: expectedHarvestOn,
      ),
    );
  }

  Future<void> _updateGrowthStage(CropSeason season) async {
    String? selected = _growthStageOptions.contains(season.growthStage)
        ? season.growthStage
        : null;
    final accepted = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text('Giai đoạn · ${season.crop}'),
          content: DropdownButtonFormField<String?>(
            initialValue: selected,
            decoration: const InputDecoration(labelText: 'Giai đoạn hiện tại'),
            items: [
              const DropdownMenuItem<String?>(
                value: null,
                child: Text('Chưa xác định'),
              ),
              ..._growthStageOptions.map(
                (stage) =>
                    DropdownMenuItem<String?>(value: stage, child: Text(stage)),
              ),
            ],
            onChanged: (value) => setDialogState(() => selected = value),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Hủy'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Lưu giai đoạn'),
            ),
          ],
        ),
      ),
    );
    if (accepted != true) return;
    await _run(
      () async =>
          ApiService.updateCropSeason(season.id, {'growth_stage': selected}),
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
                  tooltip: 'Cập nhật GPS',
                  onPressed: _busy ? null : () => _editPlotLocation(plot),
                  icon: const Icon(Icons.edit_location_alt_outlined),
                ),
                IconButton(
                  tooltip: 'Lưu trữ thửa',
                  onPressed: _busy ? null : () => _archivePlot(plot),
                  icon: const Icon(Icons.archive_outlined),
                ),
              ],
            ),
            if (plot.latitude != null && plot.longitude != null) ...[
              const SizedBox(height: 8),
              Row(
                children: [
                  const Icon(
                    Icons.gps_fixed,
                    size: 16,
                    color: AppColors.forest,
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      '${plot.latitude!.toStringAsFixed(5)}, ${plot.longitude!.toStringAsFixed(5)}'
                      '${plot.locationAccuracyM == null ? '' : ' · ±${plot.locationAccuracyM!.round()} m'}',
                      style: const TextStyle(
                        color: AppColors.muted,
                        fontSize: 12,
                      ),
                    ),
                  ),
                ],
              ),
            ] else ...[
              const SizedBox(height: 8),
              const Text(
                'Chưa có GPS · đang dùng vị trí đại diện của tỉnh',
                style: TextStyle(color: AppColors.muted, fontSize: 12),
              ),
            ],
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
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            active.crop,
                            style: const TextStyle(fontWeight: FontWeight.w800),
                          ),
                        ),
                        IconButton(
                          tooltip: 'Cập nhật giai đoạn',
                          visualDensity: VisualDensity.compact,
                          onPressed: _busy
                              ? null
                              : () => _updateGrowthStage(active),
                          icon: const Icon(Icons.autorenew_rounded, size: 20),
                        ),
                      ],
                    ),
                    Text(
                      [
                        if (active.variety != null) 'Giống ${active.variety}',
                        active.growthStage ?? 'Chưa xác định giai đoạn',
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
