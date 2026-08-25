import 'auth_url_cleanup_stub.dart'
    if (dart.library.html) 'auth_url_cleanup_web.dart'
    as platform;

/// Return the same application route without authentication query or fragment
/// values, which may contain short-lived recovery tokens.
Uri sanitizedAuthUri(Uri uri) => Uri(
  scheme: uri.scheme,
  host: uri.host,
  port: uri.hasPort ? uri.port : null,
  path: uri.path,
);

void clearAuthCallbackFromAddressBar(Uri uri) {
  platform.replaceBrowserUrl(sanitizedAuthUri(uri));
}
