import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:jarvis_app/main.dart';

void main() {
  testWidgets('JarvisApp renders the login shell', (WidgetTester tester) async {
    await tester.pumpWidget(const JarvisApp());
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.byType(MaterialApp), findsOneWidget);
    expect(find.byType(Scaffold), findsWidgets);
  });
}
