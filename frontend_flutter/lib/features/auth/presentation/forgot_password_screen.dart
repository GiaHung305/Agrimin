import 'package:flutter/material.dart';

import 'package:frontend_flutter/data/services/auth_service.dart';
import 'package:frontend_flutter/design_system/design_system.dart';
import 'package:frontend_flutter/features/auth/presentation/widgets/auth_scaffold.dart';

class ForgotPasswordScreen extends StatefulWidget {
  const ForgotPasswordScreen({super.key});

  @override
  State<ForgotPasswordScreen> createState() => _ForgotPasswordScreenState();
}

class _ForgotPasswordScreenState extends State<ForgotPasswordScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  bool _loading = false;
  bool _sent = false;
  String? _error;

  @override
  void dispose() {
    _emailController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    final error = await AuthService.requestPasswordReset(
      _emailController.text.trim(),
    );
    if (!mounted) return;
    setState(() {
      _loading = false;
      _sent = error == null;
      _error = error;
    });
  }

  @override
  Widget build(BuildContext context) => AuthScaffold(
    showBackButton: true,
    title: 'Lấy lại mật khẩu',
    subtitle: 'AgriMind sẽ gửi một liên kết bảo mật đến email của bạn.',
    form: _sent
        ? Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              AppStatusBanner.success(
                message:
                    'Nếu email đã đăng ký, liên kết đặt lại mật khẩu đã được gửi. Hãy kiểm tra cả thư rác.',
              ),
              const SizedBox(height: AppSpacing.lg),
              AppPrimaryButton(
                label: 'Quay lại đăng nhập',
                icon: Icons.login_rounded,
                onPressed: () => Navigator.maybePop(context),
              ),
            ],
          )
        : Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                AppTextField(
                  key: const Key('forgot-password-email'),
                  controller: _emailController,
                  label: 'Email',
                  hint: 'tenban@email.com',
                  prefixIcon: Icons.alternate_email_rounded,
                  keyboardType: TextInputType.emailAddress,
                  validator: (value) =>
                      RegExp(
                        r'^[^\s@]+@[^\s@]+\.[^\s@]+$',
                      ).hasMatch(value?.trim() ?? '')
                      ? null
                      : 'Vui lòng nhập email hợp lệ.',
                ),
                if (_error != null) ...[
                  const SizedBox(height: AppSpacing.sm),
                  AppStatusBanner.error(message: _error!),
                ],
                const SizedBox(height: AppSpacing.lg),
                AppPrimaryButton(
                  key: const Key('forgot-password-submit'),
                  label: 'Gửi liên kết',
                  icon: Icons.mark_email_unread_outlined,
                  isLoading: _loading,
                  onPressed: _submit,
                ),
              ],
            ),
          ),
    footer: TextButton(
      onPressed: () => Navigator.maybePop(context),
      child: const Text('Quay lại đăng nhập'),
    ),
  );
}
