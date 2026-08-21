# AgriMind Flutter

Ứng dụng production cho chat SSE, công việc, thông báo và quản lý nông trại.

## Cấu trúc `lib/`

```text
app/              # AgriMindApp, AppGate và HomeShell
data/
  models/         # DTO ánh xạ API
  services/       # auth, REST/SSE và push notification
design_system/
  foundations/    # color, spacing và radius tokens
  theme/          # Material 3 ThemeData
  components/     # component dùng chung xuyên feature
features/
  admin/
  assistant/
  auth/
  farm/
  notifications/
  tasks/
```

Feature UI import public design system qua:

```dart
import 'package:frontend_flutter/design_system/design_system.dart';
```

Không tạo thêm luồng chat ngoài `ApiService.sendMessageStream`, vì
`POST /api/v1/chat/stream` là workflow production duy nhất.

## Kiểm tra

```powershell
flutter analyze lib
flutter test
flutter build apk --debug
```

Chi tiết token và quy tắc component nằm tại
[`../docs/design-system/flutter-design-system.md`](../docs/design-system/flutter-design-system.md).
