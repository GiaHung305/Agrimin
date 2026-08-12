class CropSeason {
  const CropSeason({
    required this.id,
    required this.plotId,
    required this.crop,
    required this.status,
    this.variety,
    this.growthStage,
    this.plantedOn,
    this.expectedHarvestOn,
    this.endedAt,
  });

  final String id;
  final String plotId;
  final String crop;
  final String? variety;
  final String? growthStage;
  final DateTime? plantedOn;
  final DateTime? expectedHarvestOn;
  final String status;
  final DateTime? endedAt;

  bool get isActive => status == 'active';

  factory CropSeason.fromJson(Map<String, dynamic> json) => CropSeason(
    id: json['id']?.toString() ?? '',
    plotId: json['plot_id']?.toString() ?? '',
    crop: json['crop']?.toString() ?? '',
    variety: json['variety']?.toString(),
    growthStage: json['growth_stage']?.toString(),
    plantedOn: DateTime.tryParse(json['planted_on']?.toString() ?? ''),
    expectedHarvestOn: DateTime.tryParse(
      json['expected_harvest_on']?.toString() ?? '',
    ),
    status: json['status']?.toString() ?? 'planned',
    endedAt: DateTime.tryParse(json['ended_at']?.toString() ?? ''),
  );
}

class FarmPlot {
  const FarmPlot({
    required this.id,
    required this.name,
    required this.status,
    required this.seasons,
    this.areaHa,
    this.locationNote,
  });

  final String id;
  final String name;
  final double? areaHa;
  final String? locationNote;
  final String status;
  final List<CropSeason> seasons;

  CropSeason? get activeSeason {
    for (final season in seasons) {
      if (season.isActive) return season;
    }
    return null;
  }

  factory FarmPlot.fromJson(Map<String, dynamic> json) => FarmPlot(
    id: json['id']?.toString() ?? '',
    name: json['name']?.toString() ?? '',
    areaHa: (json['area_ha'] as num?)?.toDouble(),
    locationNote: json['location_note']?.toString(),
    status: json['status']?.toString() ?? 'active',
    seasons: (json['seasons'] as List<dynamic>? ?? const [])
        .map((item) => CropSeason.fromJson(item as Map<String, dynamic>))
        .toList(),
  );
}
