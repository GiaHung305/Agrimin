import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../services/auth_service.dart';
import '../theme/app_theme.dart';
import 'home_shell.dart';
import 'farm_profile_screen.dart';
import 'login_screen.dart';

class AppGate extends StatefulWidget {
  const AppGate({super.key});

  @override
  State<AppGate> createState() => _AppGateState();
}

class _AppGateState extends State<AppGate> {
  Widget? _destination;

  @override
  void initState() {
    super.initState();
    _resolveDestination();
  }

  Future<void> _resolveDestination() async {
    final token = await AuthService.getToken();
    if (!mounted) return;
    if (token == null) {
      setState(() => _destination = const LoginScreen());
      return;
    }
    try {
      final profile = await ApiService.getFarmProfile();
      if (!mounted) return;
      setState(
        () => _destination = profile == null
            ? const FarmProfileScreen(onboarding: true)
            : const HomeShell(),
      );
    } catch (_) {
      if (mounted) setState(() => _destination = const HomeShell());
    }
  }

  @override
  Widget build(BuildContext context) =>
      _destination ??
      const Scaffold(
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              CircleAvatar(
                radius: 30,
                backgroundColor: AppColors.forest,
                child: Icon(Icons.spa_rounded, color: AppColors.lime, size: 32),
              ),
              SizedBox(height: 16),
              Text(
                'Đang chuẩn bị AgriMind…',
                style: TextStyle(color: AppColors.muted),
              ),
            ],
          ),
        ),
      );
}
