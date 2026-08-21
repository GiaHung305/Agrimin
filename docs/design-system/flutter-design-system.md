# Design system Flutter của AgriMind

## Mục tiêu

Design system giữ cho bốn khu vực Trợ lý, Công việc, Thông báo và Nông trại có
cùng ngôn ngữ thị giác. Nó không chỉ là bảng màu: foundation tạo quy tắc, theme
đưa quy tắc vào Material 3, component đóng gói mẫu tương tác dùng lại.

## Cấu trúc

```text
lib/design_system/
├── design_system.dart            # public barrel import
├── foundations/
│   ├── app_colors.dart           # màu semantic, không đặt theo màn hình
│   ├── app_radius.dart           # cấp bo góc
│   ├── app_spacing.dart          # thang khoảng cách
│   └── app_typography.dart       # phân cấp chữ của sản phẩm
├── theme/
│   └── app_theme.dart            # Material 3 ThemeData
└── components/
    └── status_badge_icon.dart    # badge trạng thái có semantics
```

UI chỉ cần import:

```dart
import 'package:frontend_flutter/design_system/design_system.dart';
```

## Foundation hiện có

### Màu

- Brand: `forest`, `forestDark`, `mint`, `lime`.
- Neutral: `background`, `surface`, `surfaceDisabled`, `ink`, `muted`, `line`.
- Success: `success`, `successSurface`, `successSurfaceStrong`.
- Warning: `warning`, `warningDark`, `warningSurface`, `warningBorder`.
- Danger: `danger`, `dangerDark`, `dangerSurface`.

Tên token mô tả vai trò, không mô tả một màn hình. Ví dụ dùng
`AppColors.warningSurface`, không tạo `farmWarningYellow`.

### Spacing

Thang `xxs, xs, sm, md, lg, xl, xxl, section` thay thế các khoảng cách lặp lại.
Một giá trị đặc thù vẫn được phép khi nó biểu diễn kích thước kỹ thuật, nhưng
không nên tạo thêm spacing gần giống token hiện có.

### Radius

`small`, `control`, `input`, `card`, `hero`, `pill` phản ánh cấp component.

### Typography

`AppTypography` thiết lập font, độ đậm, letter spacing và line height ở cấp
`ThemeData`. Màn hình lấy style từ `Theme.of(context).textTheme`; chỉ override
thuộc tính khi cần thể hiện một cấp thông tin riêng có chủ đích.

## Quy tắc component

Đưa widget vào `design_system/components` khi:

1. được dùng ở từ hai feature trở lên;
2. có visual state hoặc accessibility semantics ổn định;
3. không chứa nghiệp vụ riêng của một feature.

Widget riêng của chat như `MessageBubble`, `TracePanel`, `ChatInput` nằm trong
`features/assistant/presentation/widgets`, không phải component toàn hệ thống.

## Accessibility và trạng thái

- Badge phải có semantic label cho cả trạng thái bật/tắt.
- Màu không được là tín hiệu duy nhất; luôn kèm icon, label hoặc trạng thái control.
- Loading, empty, error và disabled phải dùng semantic token tương ứng.
- Text/body ưu tiên typography từ `Theme.of(context).textTheme`; chỉ override
  khi có lý do phân cấp thông tin rõ ràng.

## Checklist khi thêm màn hình

- [ ] Đặt màn hình trong đúng feature.
- [ ] Dùng `AppColors`, `AppSpacing`, `AppRadius` trước khi hardcode.
- [ ] Dùng component Material 3 và theme chung.
- [ ] Có loading, empty, error, offline và retry phù hợp.
- [ ] Kiểm tra màn hình hẹp, web rộng và text scale.
- [ ] Sau `await`, kiểm tra `mounted` trước `context`/`setState`.
- [ ] Chạy `flutter analyze lib` và widget test liên quan.
