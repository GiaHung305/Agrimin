enum RegistrationStatus { authenticated, confirmationRequired, failed }

class RegistrationResult {
  const RegistrationResult._({required this.status, this.message});

  const RegistrationResult.authenticated()
    : this._(status: RegistrationStatus.authenticated);

  const RegistrationResult.confirmationRequired()
    : this._(status: RegistrationStatus.confirmationRequired);

  const RegistrationResult.failed(String message)
    : this._(status: RegistrationStatus.failed, message: message);

  final RegistrationStatus status;
  final String? message;

  bool get isAuthenticated => status == RegistrationStatus.authenticated;
  bool get requiresConfirmation =>
      status == RegistrationStatus.confirmationRequired;
}
