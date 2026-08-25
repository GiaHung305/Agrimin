class UserSession {
  const UserSession({
    required this.userId,
    required this.email,
    required this.role,
    required this.permissions,
  });

  final String userId;
  final String email;
  final String role;
  final Set<String> permissions;

  bool get isAdmin => role == 'admin';
  bool get canManageDocuments => permissions.contains('document:manage');
  bool get canViewOperations => permissions.contains('operations:view');

  factory UserSession.fromJson(Map<String, dynamic> json) => UserSession(
    userId: json['user_id']?.toString() ?? '',
    email: json['email']?.toString() ?? '',
    role: json['role']?.toString() ?? 'user',
    permissions: (json['permissions'] as List<dynamic>? ?? const [])
        .map((permission) => permission.toString())
        .toSet(),
  );
}
