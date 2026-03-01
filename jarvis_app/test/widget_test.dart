import 'package:flutter_test/flutter_test.dart';

import 'package:jarvis_app/config/api_config.dart';

void main() {
  test('API config smoke test', () {
    expect(ApiConfig.baseUrl, startsWith('http'));
    expect(ApiConfig.wsUrl, startsWith('ws'));
  });
}
