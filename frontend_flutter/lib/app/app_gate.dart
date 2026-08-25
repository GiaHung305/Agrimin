import 'package:flutter/material.dart';

import 'package:frontend_flutter/data/services/api_service.dart';
import 'package:frontend_flutter/data/services/auth_service.dart';
import 'package:frontend_flutter/design_system/design_system.dart';
import 'package:frontend_flutter/features/auth/presentation/login_screen.dart';
import 'package:frontend_flutter/features/auth/presentation/reset_password_screen.dart';
import 'package:frontend_flutter/features/farm/presentation/farm_profile_screen.dart';

import 'home_shell.dart';

class AppGate extends StatefulWidget {
  const AppGate({super.key});

  @override
  State<AppGate> createState() => _AppGateState();
}

class _AppGateState extends State<AppGate> {
  Widget? _destination;
  String? _error;

  @override
  void initState() {
    super.initState();
    _resolveDestination();
  }

  Future<void> _resolveDestination() async {
    try {
      if (await AuthService.consumeRecoverySession(Uri.base)) {
        if (mounted) {
          setState(() => _destination = const ResetPasswordScreen());
        }
        return;
      }
      final token = await AuthService.getToken();
      if (!mounted) return;
      if (token == null) {
        setState(() => _destination = const LoginScreen());
        return;
      }
      final session = await ApiService.getCurrentSession();
      final profile = await ApiService.getFarmProfile();
      if (!mounted) return;
      setState(
        () => _destination = profile == null
            ? FarmProfileScreen(
                onboarding: true,
                canManageDocuments: session.canManageDocuments,
                canViewOperations: session.canViewOperations,
              )
            : HomeShell(
                canManageDocuments: session.canManageDocuments,
                canViewOperations: session.canViewOperations,
              ),
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      if (error.isUnauthorized) {
        await AuthService.clearLocalSession();
        if (mounted) setState(() => _destination = const LoginScreen());
        return;
      }
      setState(() => _error = error.message);
    } catch (_) {
      if (mounted) {
        setState(
          () => _error =
              'Chưa thể kết nối với AgriMind. Bạn kiểm tra mạng rồi thử lại.',
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_destination != null) return _destination!;
    if (_error != null) {
      return Scaffold(
        body: AppStateView.error(
          title: 'Chưa thể mở ứng dụng',
          message: _error!,
          actionLabel: 'Thử lại',
          onAction: () {
            setState(() => _error = null);
            _resolveDestination();
          },
        ),
      );
    }
    return const Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircleAvatar(
              radius: 30,
              backgroundColor: AppColors.forest,
              child: Icon(Icons.spa_rounded, color: AppColors.lime, size: 32),
            ),
            SizedBox(height: AppSpacing.md),
            Text(
              'Đang chuẩn bị AgriMind…',
              style: TextStyle(color: AppColors.muted),
            ),
          ],
        ),
      ),
    );
  }
}
