class FarmProfile {
  const FarmProfile({
    required this.id,
    required this.name,
    this.province,
    this.crop,
    this.areaHa,
    this.farmingStyle,
  });

  final String id;
  final String name;
  final String? province;
  final String? crop;
  final double? areaHa;
  final String? farmingStyle;

  factory FarmProfile.fromJson(Map<String, dynamic> json) => FarmProfile(
    id: json['id']?.toString() ?? '',
    name: json['name']?.toString() ?? 'Nông trại của tôi',
    province: json['province']?.toString(),
    crop: json['crop']?.toString(),
    areaHa: (json['area_ha'] as num?)?.toDouble(),
    farmingStyle: json['farming_style']?.toString(),
  );
}
