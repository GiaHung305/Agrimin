import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend_flutter/design_system/design_system.dart';

void main() {
  Future<void> renderShowcase(
    WidgetTester tester, {
    required ThemeMode themeMode,
  }) async {
    tester.view.physicalSize = const Size(800, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        darkTheme: buildAppDarkTheme(),
        themeMode: themeMode,
        home: const _DesignSystemShowcase(),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('design system light visual regression', (tester) async {
    await renderShowcase(tester, themeMode: ThemeMode.light);
    await expectLater(
      find.byKey(const Key('design-system-showcase')),
      matchesGoldenFile('goldens/design_system_light.png'),
    );
  });

  testWidgets('design system dark visual regression', (tester) async {
    await renderShowcase(tester, themeMode: ThemeMode.dark);
    await expectLater(
      find.byKey(const Key('design-system-showcase')),
      matchesGoldenFile('goldens/design_system_dark.png'),
    );
  });
}

class _DesignSystemShowcase extends StatefulWidget {
  const _DesignSystemShowcase();

  @override
  State<_DesignSystemShowcase> createState() => _DesignSystemShowcaseState();
}

class _DesignSystemShowcaseState extends State<_DesignSystemShowcase> {
  final controller = TextEditingController(text: 'Bắp cải vụ mùa');

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: RepaintBoundary(
      key: const Key('design-system-showcase'),
      child: ColoredBox(
        color: Theme.of(context).scaffoldBackgroundColor,
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpacing.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'AgriMind Design System',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: AppSpacing.lg),
              AppTextField(
                controller: controller,
                label: 'Mùa vụ',
                prefixIcon: Icons.eco_outlined,
              ),
              const SizedBox(height: AppSpacing.md),
              const AppStatusBanner.success(
                message: 'Worker đang hoạt động bình thường.',
              ),
              const SizedBox(height: AppSpacing.sm),
              const AppStatusBanner.warning(
                message: 'Có một thông báo đang chờ gửi lại.',
              ),
              const SizedBox(height: AppSpacing.md),
              AppCard(
                child: ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.agriculture_outlined),
                  title: const Text('Thửa xà lách'),
                  subtitle: const Text('1 ha · đang canh tác'),
                  trailing: const Icon(Icons.chevron_right_rounded),
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              AppPrimaryButton(
                label: 'Lưu thay đổi',
                icon: Icons.check_rounded,
                onPressed: () {},
              ),
              const SizedBox(height: AppSpacing.xl),
              const SizedBox(
                height: 230,
                child: AppEmptyState(
                  title: 'Chưa có công việc',
                  message: 'Công việc mới sẽ xuất hiện tại đây.',
                ),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}
