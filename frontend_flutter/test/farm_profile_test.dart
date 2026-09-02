import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:frontend_flutter/data/models/farm_profile.dart';
import 'package:frontend_flutter/features/farm/presentation/farm_profile_screen.dart';

void main() {
  test('FarmProfile parses API numbers and blank optional values safely', () {
    final profile = FarmProfile.fromJson({
      'id': 'farm-1',
      'name': ' Nông trại A ',
      'province': ' ',
      'area_ha': '2,5',
      'farming_style': null,
    });

    expect(profile.id, 'farm-1');
    expect(profile.name, 'Nông trại A');
    expect(profile.province, isNull);
    expect(profile.areaHa, 2.5);
    expect(profile.farmingStyle, isNull);
  });

  testWidgets('saved farm profile is shown in every form field', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: FarmProfileScreen(
          loadProfile: () async => const FarmProfile(
            id: 'farm-1',
            name: 'Nông trại Đồi Gió',
            province: 'Lâm Đồng',
            areaHa: 2.5,
            farmingStyle: 'Hữu cơ',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    String value(Key key) =>
        tester.widget<TextFormField>(find.byKey(key)).controller!.text;

    expect(value(const Key('farm-profile-name')), 'Nông trại Đồi Gió');
    expect(value(const Key('farm-profile-province')), 'Lâm Đồng');
    expect(value(const Key('farm-profile-area')), '2.5');
    expect(value(const Key('farm-profile-style')), 'Hữu cơ');
  });

  testWidgets('zero farm area is rejected before saving', (tester) async {
    var saveCalls = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: FarmProfileScreen(
          loadProfile: () async => null,
          saveProfile: ({required name, province, areaHa, farmingStyle}) async {
            saveCalls += 1;
            return FarmProfile(id: 'farm-1', name: name, areaHa: areaHa);
          },
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.enterText(find.byKey(const Key('farm-profile-area')), '0');
    await tester.ensureVisible(find.text('Lưu thay đổi'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Lưu thay đổi'));
    await tester.pump();

    expect(find.text('Diện tích cần lớn hơn 0 ha.'), findsOneWidget);
    expect(saveCalls, 0);
  });
}
