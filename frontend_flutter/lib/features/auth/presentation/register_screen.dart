import 'package:flutter/material.dart';

import 'package:frontend_flutter/app/app_gate.dart';
import 'package:frontend_flutter/data/models/registration_result.dart';
import 'package:frontend_flutter/data/services/auth_service.dart';
import 'package:frontend_flutter/design_system/design_system.dart';
import 'package:frontend_flutter/features/auth/presentation/widgets/auth_scaffold.dart';

typedef RegisterAccount =
    Future<RegistrationResult> Function({
      required String email,
      required String password,
      required String displayName,
    });

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key, this.onRegister});

  final RegisterAccount? onRegister;

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmController = TextEditingController();

  bool _isLoading = false;
  bool _obscurePassword = true;
  bool _obscureConfirmation = true;
  bool _confirmationSent = false;
  String? _error;

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    _confirmController.dispose();
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
      final register = widget.onRegister ?? AuthService.register;
      final result = await register(
        email: _emailController.text.trim(),
        password: _passwordController.text,
        displayName: _nameController.text.trim(),
      );
      if (!mounted) return;

      if (result.isAuthenticated) {
        Navigator.of(context).pushAndRemoveUntil(
          MaterialPageRoute(builder: (_) => const AppGate()),
          (_) => false,
        );
        return;
      }
      if (result.requiresConfirmation) {
        setState(() {
          _isLoading = false;
          _confirmationSent = true;
        });
        return;
      }
      setState(() {
        _isLoading = false;
        _error = result.message;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _isLoading = false;
        _error = 'Không thể kết nối để đăng ký. Bạn kiểm tra mạng rồi thử lại.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_confirmationSent) return _buildConfirmationState();

    return AuthScaffold(
      showBackButton: true,
      title: 'Tạo tài khoản mới',
      subtitle:
          'Thiết lập tài khoản để AgriMind đồng hành cùng từng thửa đất và mùa vụ của bạn.',
      form: Form(
        key: _formKey,
        child: AutofillGroup(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextFormField(
                key: const Key('register-name-field'),
                controller: _nameController,
                textCapitalization: TextCapitalization.words,
                textInputAction: TextInputAction.next,
                autofillHints: const [AutofillHints.name],
                decoration: const InputDecoration(
                  labelText: 'Tên của bạn',
                  hintText: 'Ví dụ: Nguyễn Văn An',
                  prefixIcon: Icon(Icons.person_outline_rounded),
                ),
                validator: (value) => (value?.trim().length ?? 0) < 2
                    ? 'Vui lòng nhập tên của bạn.'
                    : null,
              ),
              const SizedBox(height: AppSpacing.sm),
              TextFormField(
                key: const Key('register-email-field'),
                controller: _emailController,
                keyboardType: TextInputType.emailAddress,
                textInputAction: TextInputAction.next,
                autofillHints: const [AutofillHints.email],
                decoration: const InputDecoration(
                  labelText: 'Email',
                  hintText: 'tenban@email.com',
                  prefixIcon: Icon(Icons.alternate_email_rounded),
                ),
                validator: _validateEmail,
              ),
              const SizedBox(height: AppSpacing.sm),
              TextFormField(
                key: const Key('register-password-field'),
                controller: _passwordController,
                obscureText: _obscurePassword,
                textInputAction: TextInputAction.next,
                autofillHints: const [AutofillHints.newPassword],
                onChanged: (_) => setState(() {}),
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
                validator: (value) => (value?.length ?? 0) < 8
                    ? 'Mật khẩu cần ít nhất 8 ký tự.'
                    : null,
              ),
              const SizedBox(height: AppSpacing.xs),
              _PasswordStrength(password: _passwordController.text),
              const SizedBox(height: AppSpacing.sm),
              TextFormField(
                key: const Key('register-confirm-field'),
                controller: _confirmController,
                obscureText: _obscureConfirmation,
                textInputAction: TextInputAction.done,
                autofillHints: const [AutofillHints.newPassword],
                onFieldSubmitted: (_) => _isLoading ? null : _submit(),
                decoration: InputDecoration(
                  labelText: 'Nhập lại mật khẩu',
                  prefixIcon: const Icon(Icons.verified_user_outlined),
                  suffixIcon: IconButton(
                    tooltip: _obscureConfirmation
                        ? 'Hiện mật khẩu xác nhận'
                        : 'Ẩn mật khẩu xác nhận',
                    onPressed: () => setState(
                      () => _obscureConfirmation = !_obscureConfirmation,
                    ),
                    icon: Icon(
                      _obscureConfirmation
                          ? Icons.visibility_off_outlined
                          : Icons.visibility_outlined,
                    ),
                  ),
                ),
                validator: (value) => value != _passwordController.text
                    ? 'Hai mật khẩu chưa trùng nhau.'
                    : null,
              ),
              if (_error != null) ...[
                const SizedBox(height: AppSpacing.sm),
                AuthNotice.error(_error!),
              ],
              const SizedBox(height: AppSpacing.lg),
              FilledButton.icon(
                key: const Key('register-submit-button'),
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
                    : const Icon(Icons.person_add_alt_1_rounded),
                label: Text(_isLoading ? 'Đang tạo tài khoản…' : 'Đăng ký'),
              ),
            ],
          ),
        ),
      ),
      footer: TextButton(
        onPressed: () => Navigator.maybePop(context),
        child: const Text('Đã có tài khoản? Đăng nhập'),
      ),
    );
  }

  Widget _buildConfirmationState() => AuthScaffold(
    showBackButton: true,
    title: 'Kiểm tra email của bạn',
    subtitle: 'Tài khoản đã được tạo và chỉ còn một bước xác minh.',
    form: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Icon(
          Icons.mark_email_read_outlined,
          size: 52,
          color: AppColors.forest,
        ),
        const SizedBox(height: AppSpacing.md),
        AuthNotice.success(
          'AgriMind đã gửi liên kết xác minh đến ${_emailController.text.trim()}. '
          'Hãy mở email, xác nhận tài khoản rồi quay lại đăng nhập.',
        ),
        const SizedBox(height: AppSpacing.lg),
        FilledButton.icon(
          onPressed: () => Navigator.maybePop(context),
          icon: const Icon(Icons.login_rounded),
          label: const Text('Quay lại đăng nhập'),
        ),
      ],
    ),
    footer: const SizedBox.shrink(),
  );

  String? _validateEmail(String? value) {
    final email = value?.trim() ?? '';
    final valid = RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$').hasMatch(email);
    return valid ? null : 'Vui lòng nhập email hợp lệ.';
  }
}

class _PasswordStrength extends StatelessWidget {
  const _PasswordStrength({required this.password});

  final String password;

  @override
  Widget build(BuildContext context) {
    final score = _score(password);
    final label = switch (score) {
      0 || 1 => 'Mật khẩu còn yếu',
      2 => 'Mật khẩu khá',
      _ => 'Mật khẩu tốt',
    };
    final color = switch (score) {
      0 || 1 => AppColors.danger,
      2 => AppColors.warning,
      _ => AppColors.success,
    };

    return Semantics(
      label: label,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: List.generate(
              3,
              (index) => Expanded(
                child: Container(
                  height: 4,
                  margin: EdgeInsets.only(right: index == 2 ? 0 : 5),
                  decoration: BoxDecoration(
                    color: index < score ? color : AppColors.line,
                    borderRadius: BorderRadius.circular(AppRadius.pill),
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            '$label · Dùng ít nhất 8 ký tự, thêm số hoặc ký tự đặc biệt.',
            style: const TextStyle(color: AppColors.muted, fontSize: 12),
          ),
        ],
      ),
    );
  }

  int _score(String value) {
    if (value.isEmpty) return 0;
    var score = value.length >= 8 ? 1 : 0;
    if (RegExp(r'[A-Za-z]').hasMatch(value) &&
        RegExp(r'[0-9]').hasMatch(value)) {
      score++;
    }
    if (RegExp(r'[^A-Za-z0-9]').hasMatch(value)) score++;
    return score.clamp(1, 3);
  }
}
