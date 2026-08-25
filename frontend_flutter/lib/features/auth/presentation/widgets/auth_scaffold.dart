import 'package:flutter/material.dart';

import 'package:frontend_flutter/design_system/design_system.dart';

class AuthScaffold extends StatelessWidget {
  const AuthScaffold({
    super.key,
    required this.title,
    required this.subtitle,
    required this.form,
    required this.footer,
    this.showBackButton = false,
  });

  final String title;
  final String subtitle;
  final Widget form;
  final Widget footer;
  final bool showBackButton;

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.sizeOf(context);
    return Scaffold(
      body: SafeArea(
        child: Stack(
          children: [
            const Positioned.fill(child: _AuthBackdrop()),
            Center(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(
                  AppSpacing.xl,
                  AppSpacing.lg,
                  AppSpacing.xl,
                  AppSpacing.xxl,
                ),
                child: ConstrainedBox(
                  constraints: BoxConstraints(
                    maxWidth: AppBreakpoints.formMax,
                    minHeight: size.height - 96,
                  ),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Row(
                        children: [
                          if (showBackButton) ...[
                            IconButton.filledTonal(
                              tooltip: 'Quay lại đăng nhập',
                              onPressed: () => Navigator.maybePop(context),
                              icon: const Icon(Icons.arrow_back_rounded),
                            ),
                            const SizedBox(width: AppSpacing.sm),
                          ],
                          const Expanded(child: AuthBrandMark()),
                        ],
                      ),
                      const SizedBox(height: AppSpacing.xxl),
                      Text(
                        title,
                        style: Theme.of(context).textTheme.headlineSmall,
                      ),
                      const SizedBox(height: AppSpacing.xs),
                      Text(
                        subtitle,
                        style: Theme.of(
                          context,
                        ).textTheme.bodyLarge?.copyWith(color: AppColors.muted),
                      ),
                      const SizedBox(height: AppSpacing.xl),
                      AuthCard(child: form),
                      const SizedBox(height: AppSpacing.md),
                      footer,
                      const SizedBox(height: AppSpacing.lg),
                      const _PrivacyNote(),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class AuthCard extends StatelessWidget {
  const AuthCard({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(AppSpacing.lg),
    decoration: BoxDecoration(
      color: AppColors.surface,
      borderRadius: BorderRadius.circular(AppRadius.hero),
      border: Border.all(color: AppColors.line),
      boxShadow: const [
        BoxShadow(
          color: AppColors.softOverlay,
          blurRadius: 22,
          offset: Offset(0, 8),
        ),
      ],
    ),
    child: child,
  );
}

class AuthBrandMark extends StatelessWidget {
  const AuthBrandMark({super.key});

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Container(
        width: 52,
        height: 52,
        decoration: const BoxDecoration(
          color: AppColors.forest,
          shape: BoxShape.circle,
        ),
        child: const Icon(Icons.spa_rounded, color: AppColors.lime, size: 28),
      ),
      const SizedBox(width: AppSpacing.sm),
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'AgriMind',
            style: Theme.of(
              context,
            ).textTheme.titleLarge?.copyWith(color: AppColors.forestDark),
          ),
          const Text(
            'TRỢ LÝ NÔNG NGHIỆP',
            style: TextStyle(
              color: AppColors.muted,
              fontSize: 10,
              fontWeight: FontWeight.w700,
              letterSpacing: 1.15,
            ),
          ),
        ],
      ),
    ],
  );
}

class _AuthBackdrop extends StatelessWidget {
  const _AuthBackdrop();

  @override
  Widget build(BuildContext context) => DecoratedBox(
    decoration: const BoxDecoration(
      gradient: LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [AppColors.background, AppColors.mint],
      ),
    ),
    child: Align(
      alignment: const Alignment(1.15, -1.1),
      child: Container(
        width: 210,
        height: 210,
        decoration: const BoxDecoration(
          color: AppColors.onPrimarySubtle,
          shape: BoxShape.circle,
        ),
      ),
    ),
  );
}

class _PrivacyNote extends StatelessWidget {
  const _PrivacyNote();

  @override
  Widget build(BuildContext context) => const Row(
    mainAxisAlignment: MainAxisAlignment.center,
    children: [
      Icon(Icons.shield_outlined, size: 17, color: AppColors.forest),
      SizedBox(width: AppSpacing.xs),
      Flexible(
        child: Text(
          'Thông tin tài khoản và nông trại được bảo vệ riêng tư.',
          textAlign: TextAlign.center,
          style: TextStyle(color: AppColors.muted, fontSize: 12),
        ),
      ),
    ],
  );
}
