import 'package:flutter/material.dart';

import 'package:frontend_flutter/data/services/auth_service.dart';
import 'package:frontend_flutter/design_system/design_system.dart';
import 'package:frontend_flutter/features/auth/presentation/login_screen.dart';
import 'package:frontend_flutter/features/auth/presentation/widgets/auth_scaffold.dart';

class ResetPasswordScreen extends StatefulWidget {
  const ResetPasswordScreen({super.key});

  @override
  State<ResetPasswordScreen> createState() => _ResetPasswordScreenState();
}

class _ResetPasswordScreenState extends State<ResetPasswordScreen> {
  final _formKey = GlobalKey<FormState>();
  final _password = TextEditingController();
  final _confirmation = TextEditingController();
  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    _password.dispose();
    _confirmation.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    final error = await AuthService.updatePassword(_password.text);
    if (!mounted) return;
    if (error != null) {
      setState(() {
        _loading = false;
        _error = error;
      });
      return;
    }
    await AuthService.logout();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const LoginScreen()),
      (_) => false,
    );
    AppSnackbar.success(context, 'Đã đổi mật khẩu. Bạn hãy đăng nhập lại.');
  }

  @override
  Widget build(BuildContext context) => AuthScaffold(
    title: 'Tạo mật khẩu mới',
    subtitle: 'Chọn mật khẩu mới có ít nhất 8 ký tự.',
    form: Form(
      key: _formKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          AppTextField(
            controller: _password,
            label: 'Mật khẩu mới',
            prefixIcon: Icons.lock_reset_rounded,
            obscureText: true,
            validator: (value) => (value?.length ?? 0) < 8
                ? 'Mật khẩu cần ít nhất 8 ký tự.'
                : null,
          ),
          const SizedBox(height: AppSpacing.sm),
          AppTextField(
            controller: _confirmation,
            label: 'Nhập lại mật khẩu',
            prefixIcon: Icons.verified_user_outlined,
            obscureText: true,
            validator: (value) => value != _password.text
                ? 'Hai mật khẩu chưa trùng nhau.'
                : null,
          ),
          if (_error != null) ...[
            const SizedBox(height: AppSpacing.sm),
            AppStatusBanner.error(message: _error!),
          ],
          const SizedBox(height: AppSpacing.lg),
          AppPrimaryButton(
            label: 'Cập nhật mật khẩu',
            icon: Icons.password_rounded,
            isLoading: _loading,
            onPressed: _submit,
          ),
        ],
      ),
    ),
    footer: const SizedBox.shrink(),
  );
}
