class FarmProfile {
  const FarmProfile({
    required this.id,
    required this.name,
    this.province,
    this.areaHa,
    this.farmingStyle,
  });

  final String id;
  final String name;
  final String? province;
  final double? areaHa;
  final String? farmingStyle;

  factory FarmProfile.fromJson(Map<String, dynamic> json) {
    final name = _optionalText(json['name']);
    return FarmProfile(
      id: _optionalText(json['id']) ?? '',
      name: name ?? 'Nông trại của tôi',
      province: _optionalText(json['province']),
      areaHa: _optionalDouble(json['area_ha']),
      farmingStyle: _optionalText(json['farming_style']),
    );
  }

  static String? _optionalText(dynamic value) {
    if (value == null) return null;
    final text = value.toString().trim();
    return text.isEmpty ? null : text;
  }

  static double? _optionalDouble(dynamic value) {
    if (value is num) return value.toDouble();
    if (value is String) {
      return double.tryParse(value.trim().replaceAll(',', '.'));
    }
    return null;
  }
}
