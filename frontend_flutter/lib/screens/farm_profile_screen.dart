import 'package:flutter/material.dart';

import '../models/farm_profile.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import 'home_shell.dart';

class FarmProfileScreen extends StatefulWidget {
  const FarmProfileScreen({super.key, this.onboarding = false});
  final bool onboarding;

  @override
  State<FarmProfileScreen> createState() => _FarmProfileScreenState();
}

class _FarmProfileScreenState extends State<FarmProfileScreen> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController(text: 'Nông trại của tôi');
  final _province = TextEditingController();
  final _crop = TextEditingController();
  final _area = TextEditingController();
  final _style = TextEditingController();
  bool _loading = true;
  bool _saving = false;
  String? _loadError;

  @override
  void initState() {
    super.initState();
    _loadProfile();
  }

  @override
  void dispose() {
    _name.dispose();
    _province.dispose();
    _crop.dispose();
    _area.dispose();
    _style.dispose();
    super.dispose();
  }

  Future<void> _loadProfile() async {
    setState(() {
      _loading = true;
      _loadError = null;
    });
    try {
      final profile = await ApiService.getFarmProfile();
      if (!mounted) return;
      if (profile != null) _fill(profile);
      setState(() => _loading = false);
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _loadError =
            'Chưa tải được dữ liệu cũ. Bạn vẫn có thể nhập và lưu hồ sơ mới.';
      });
    }
  }

  void _fill(FarmProfile profile) {
    _name.text = profile.name;
    _province.text = profile.province ?? '';
    _crop.text = profile.crop ?? '';
    _area.text = profile.areaHa?.toString() ?? '';
    _style.text = profile.farmingStyle ?? '';
  }

  String? _optional(TextEditingController controller) {
    final value = controller.text.trim();
    return value.isEmpty ? null : value;
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    final areaText = _area.text.trim().replaceAll(',', '.');
    final area = areaText.isEmpty ? null : double.tryParse(areaText);
    if (areaText.isNotEmpty && area == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Diện tích cần là một con số hợp lệ.')),
      );
      return;
    }
    setState(() => _saving = true);
    try {
      await ApiService.saveFarmProfile(
        name: _name.text.trim(),
        province: _optional(_province),
        crop: _optional(_crop),
        areaHa: area,
        farmingStyle: _optional(_style),
      );
      if (!mounted) return;
      if (widget.onboarding) {
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(builder: (_) => const HomeShell()),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Đã lưu hồ sơ nông trại.')),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Không thể lưu hồ sơ. Hãy thử lại.')),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final title = widget.onboarding
        ? 'Giới thiệu nông trại'
        : 'Hồ sơ nông trại';
    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: !widget.onboarding,
        title: Text(
          widget.onboarding ? 'Thiết lập AgriMind' : 'Nông trại của tôi',
        ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : SafeArea(
              top: false,
              child: Form(
                key: _formKey,
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(20, 14, 20, 32),
                  children: [
                    const _FarmHero(),
                    const SizedBox(height: 25),
                    Text(
                      title,
                      style: Theme.of(context).textTheme.headlineSmall
                          ?.copyWith(fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 7),
                    const Text(
                      'Thông tin này giúp trợ lý tư vấn, cảnh báo thời tiết và nhắc việc sát với nông trại hơn.',
                      style: TextStyle(color: AppColors.muted, height: 1.45),
                    ),
                    if (_loadError != null) ...[
                      const SizedBox(height: 15),
                      _Notice(message: _loadError!),
                    ],
                    const SizedBox(height: 24),
                    const _SectionLabel('Thông tin cơ bản'),
                    const SizedBox(height: 10),
                    TextFormField(
                      controller: _name,
                      textCapitalization: TextCapitalization.words,
                      decoration: const InputDecoration(
                        labelText: 'Tên nông trại *',
                        prefixIcon: Icon(Icons.agriculture_outlined),
                      ),
                      validator: (value) =>
                          value == null || value.trim().isEmpty
                          ? 'Hãy đặt tên cho nông trại.'
                          : null,
                    ),
                    const SizedBox(height: 13),
                    TextFormField(
                      controller: _province,
                      textCapitalization: TextCapitalization.words,
                      decoration: const InputDecoration(
                        labelText: 'Tỉnh / thành phố',
                        prefixIcon: Icon(Icons.location_on_outlined),
                      ),
                    ),
                    const SizedBox(height: 24),
                    const _SectionLabel('Canh tác'),
                    const SizedBox(height: 10),
                    TextFormField(
                      controller: _crop,
                      textCapitalization: TextCapitalization.words,
                      decoration: const InputDecoration(
                        labelText: 'Cây trồng chính',
                        hintText: 'Ví dụ: Sầu riêng, lúa, cà phê',
                        prefixIcon: Icon(Icons.eco_outlined),
                      ),
                    ),
                    const SizedBox(height: 13),
                    TextFormField(
                      controller: _area,
                      keyboardType: const TextInputType.numberWithOptions(
                        decimal: true,
                      ),
                      decoration: const InputDecoration(
                        labelText: 'Diện tích (ha)',
                        hintText: 'Ví dụ: 2.5',
                        prefixIcon: Icon(Icons.square_foot_outlined),
                      ),
                    ),
                    const SizedBox(height: 13),
                    TextFormField(
                      controller: _style,
                      textCapitalization: TextCapitalization.sentences,
                      decoration: const InputDecoration(
                        labelText: 'Phương thức canh tác',
                        hintText: 'Ví dụ: Hữu cơ, VietGAP',
                        prefixIcon: Icon(Icons.spa_outlined),
                      ),
                    ),
                    const SizedBox(height: 30),
                    FilledButton.icon(
                      onPressed: _saving ? null : _save,
                      icon: _saving
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(
                                color: Colors.white,
                                strokeWidth: 2,
                              ),
                            )
                          : const Icon(Icons.check_circle_outline_rounded),
                      label: Text(
                        widget.onboarding
                            ? 'Hoàn tất và vào trợ lý'
                            : 'Lưu thay đổi',
                      ),
                    ),
                    if (widget.onboarding) ...[
                      const SizedBox(height: 12),
                      const Text(
                        'Bạn có thể bổ sung hoặc chỉnh sửa thông tin này bất cứ lúc nào.',
                        textAlign: TextAlign.center,
                        style: TextStyle(color: AppColors.muted, fontSize: 12),
                      ),
                    ],
                  ],
                ),
              ),
            ),
    );
  }
}

class _FarmHero extends StatelessWidget {
  const _FarmHero();
  @override
  Widget build(BuildContext context) => Container(
    height: 135,
    padding: const EdgeInsets.all(21),
    decoration: BoxDecoration(
      gradient: const LinearGradient(
        colors: [AppColors.forestDark, AppColors.forest],
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
      ),
      borderRadius: BorderRadius.circular(26),
    ),
    child: Row(
      children: [
        const Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                'Thông tin đúng,\ntư vấn sát hơn.',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 19,
                  fontWeight: FontWeight.w800,
                  height: 1.2,
                ),
              ),
              SizedBox(height: 7),
              Text(
                'Cá nhân hóa AgriMind cho bạn',
                style: TextStyle(color: Color(0xFFD3EBDD), fontSize: 12),
              ),
            ],
          ),
        ),
        Container(
          width: 76,
          height: 76,
          decoration: BoxDecoration(
            color: Colors.white24,
            shape: BoxShape.circle,
          ),
          child: const Icon(
            Icons.agriculture_rounded,
            size: 39,
            color: AppColors.lime,
          ),
        ),
      ],
    ),
  );
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);
  final String text;
  @override
  Widget build(BuildContext context) => Text(
    text.toUpperCase(),
    style: const TextStyle(
      color: AppColors.forest,
      letterSpacing: .8,
      fontSize: 11,
      fontWeight: FontWeight.w800,
    ),
  );
}

class _Notice extends StatelessWidget {
  const _Notice({required this.message});
  final String message;
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(13),
    decoration: BoxDecoration(
      color: const Color(0xFFFFF8E7),
      borderRadius: BorderRadius.circular(16),
    ),
    child: Row(
      children: [
        const Icon(Icons.wifi_off_rounded, color: Color(0xFFAD7910), size: 19),
        const SizedBox(width: 9),
        Expanded(
          child: Text(
            message,
            style: const TextStyle(
              color: Color(0xFF765000),
              fontSize: 13,
              height: 1.35,
            ),
          ),
        ),
      ],
    ),
  );
}
