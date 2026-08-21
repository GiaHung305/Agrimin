import 'package:flutter/material.dart';

import 'package:frontend_flutter/app/app_gate.dart';
import 'package:frontend_flutter/data/services/auth_service.dart';
import 'package:frontend_flutter/design_system/design_system.dart';
import 'package:frontend_flutter/features/auth/presentation/register_screen.dart';
import 'package:frontend_flutter/features/auth/presentation/widgets/auth_scaffold.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _isLoading = false;
  bool _obscurePassword = true;
  String? _error;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();
    if (!(_formKey.currentState?.validate() ?? false)) return;

    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      final token = await AuthService.login(
        _emailController.text.trim(),
        _passwordController.text,
      );
      if (!mounted) return;
      if (token != null) {
        Navigator.of(context).pushAndRemoveUntil(
          MaterialPageRoute(builder: (_) => const AppGate()),
          (_) => false,
        );
        return;
      }
      setState(() {
        _isLoading = false;
        _error = 'Email hoặc mật khẩu chưa chính xác.';
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _isLoading = false;
        _error =
            'Không thể kết nối để đăng nhập. Bạn kiểm tra mạng rồi thử lại.';
      });
    }
  }

  void _openRegistration() {
    Navigator.of(
      context,
    ).push(MaterialPageRoute(builder: (_) => const RegisterScreen()));
  }

  @override
  Widget build(BuildContext context) => AuthScaffold(
    title: 'Chào mừng trở lại',
    subtitle: 'Đăng nhập để tiếp tục cùng trợ lý nông nghiệp của bạn.',
    form: Form(
      key: _formKey,
      child: AutofillGroup(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextFormField(
              key: const Key('login-email-field'),
              controller: _emailController,
              keyboardType: TextInputType.emailAddress,
              autofillHints: const [
                AutofillHints.username,
                AutofillHints.email,
              ],
              textInputAction: TextInputAction.next,
              decoration: const InputDecoration(
                labelText: 'Email',
                hintText: 'tenban@email.com',
                prefixIcon: Icon(Icons.alternate_email_rounded),
              ),
              validator: (value) => (value?.trim().isEmpty ?? true)
                  ? 'Vui lòng nhập email.'
                  : null,
            ),
            const SizedBox(height: AppSpacing.sm),
            TextFormField(
              key: const Key('login-password-field'),
              controller: _passwordController,
              obscureText: _obscurePassword,
              autofillHints: const [AutofillHints.password],
              textInputAction: TextInputAction.done,
              onFieldSubmitted: (_) => _isLoading ? null : _submit(),
              decoration: InputDecoration(
                labelText: 'Mật khẩu',
                prefixIcon: const Icon(Icons.lock_outline_rounded),
                suffixIcon: IconButton(
                  tooltip: _obscurePassword ? 'Hiện mật khẩu' : 'Ẩn mật khẩu',
                  onPressed: () =>
                      setState(() => _obscurePassword = !_obscurePassword),
                  icon: Icon(
                    _obscurePassword
                        ? Icons.visibility_off_outlined
                        : Icons.visibility_outlined,
                  ),
                ),
              ),
              validator: (value) =>
                  (value?.isEmpty ?? true) ? 'Vui lòng nhập mật khẩu.' : null,
            ),
            if (_error != null) ...[
              const SizedBox(height: AppSpacing.sm),
              AuthNotice.error(_error!),
            ],
            const SizedBox(height: AppSpacing.lg),
            FilledButton.icon(
              key: const Key('login-submit-button'),
              onPressed: _isLoading ? null : _submit,
              icon: _isLoading
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: AppColors.onPrimary,
                      ),
                    )
                  : const Icon(Icons.login_rounded),
              label: Text(_isLoading ? 'Đang đăng nhập…' : 'Đăng nhập'),
            ),
          ],
        ),
      ),
    ),
    footer: Column(
      children: [
        const Text(
          'Bạn chưa có tài khoản?',
          style: TextStyle(color: AppColors.muted),
        ),
        const SizedBox(height: AppSpacing.xs),
        OutlinedButton.icon(
          key: const Key('open-register-button'),
          onPressed: _isLoading ? null : _openRegistration,
          icon: const Icon(Icons.person_add_alt_1_rounded),
          label: const Text('Tạo tài khoản mới'),
        ),
      ],
    ),
  );
}
