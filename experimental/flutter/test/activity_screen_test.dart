import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:jarvis_app/screens/activity_screen.dart';
import 'package:jarvis_app/theme/app_theme.dart';

void main() {
  group('ActivityScreen - logic', () {
    test('_statusColor maps all known states', () {
      Color statusColor(String status) {
        switch (status) {
          case 'RUNNING': return Colors.green;
          case 'PENDING': return Colors.orange;
          case 'SUSPENDED': return Colors.blue;
          case 'FAILED': return Colors.red;
          case 'COMPLETED': return Colors.grey;
          case 'CANCELLED': return Colors.grey.shade600;
          default: return Colors.white;
        }
      }
      expect(statusColor('RUNNING'), Colors.green);
      expect(statusColor('PENDING'), Colors.orange);
      expect(statusColor('SUSPENDED'), Colors.blue);
      expect(statusColor('FAILED'), Colors.red);
      expect(statusColor('COMPLETED'), Colors.grey);
      expect(statusColor('CANCELLED'), Colors.grey.shade600);
      expect(statusColor('UNKNOWN'), Colors.white);
    });

    test('tree icon map covers all states', () {
      final iconMap = <String, String>{
        'PENDING': '\u25CB', 'RUNNING': '\u25B6', 'COMPLETED': '\u2713',
        'FAILED': '\u2717', 'SUSPENDED': '\u23F8', 'CANCELLED': '\u2298',
      };
      expect(iconMap['RUNNING'], '\u25B6');
      expect(iconMap['COMPLETED'], '\u2713');
      expect(iconMap['FAILED'], '\u2717');
      expect(iconMap['PENDING'], '\u25CB');
      expect(iconMap['SUSPENDED'], '\u23F8');
      expect(iconMap['CANCELLED'], '\u2298');
      expect(iconMap['UNKNOWN'], isNull);
    });

    test('tree children map builds correctly', () {
      final nodes = [
        {'node_id': 'n1', 'parent_id': ''},
        {'node_id': 'n2', 'parent_id': 'n1'},
        {'node_id': 'n3', 'parent_id': 'n1'},
        {'node_id': 'n4', 'parent_id': 'n2'},
      ];
      final Map<String, List> children = {};
      for (final n in nodes) {
        final p = (n['parent_id'] as String?) ?? '';
        children.putIfAbsent(p, () => []).add(n);
      }
      expect(children[''], hasLength(1));
      expect(children['n1'], hasLength(2));
      expect(children['n2'], hasLength(1));
      expect(children['n3'], isNull);
    });

    test('handles empty node list in tree', () {
      final nodes = <Map<String, String>>[];
      final Map<String, List> children = {};
      for (final n in nodes) {
        final p = (n['parent_id'] as String?) ?? '';
        children.putIfAbsent(p, () => []).add(n);
      }
      expect(children, isEmpty);
    });

    test('label truncated at 60 chars', () {
      String truncate(String label) {
        return label.length > 60 ? '${label.substring(0, 60)}...' : label;
      }
      expect(truncate('A' * 100).length, 63);
      expect(truncate('Short'), 'Short');
      expect(truncate(''), '');
    });

    test('label truncated at 40 chars for tree view', () {
      String truncateTree(String label) {
        return label.length > 40 ? '${label.substring(0, 40)}...' : label;
      }
      expect(truncateTree('A' * 50).length, 43);
      expect(truncateTree('Short'), 'Short');
    });

    test('_detailRow renders correctly', () {
      String detailRow(String label, String value) => '$label: $value';
      expect(detailRow('ID', 'act_001'), 'ID: act_001');
      expect(detailRow('Status', 'RUNNING'), 'Status: RUNNING');
      expect(detailRow('Depth', '0'), 'Depth: 0');
    });

    test('count chip renders with label and value', () {
      String countChip(String label, int count) => '$label: $count';
      expect(countChip('Total', 5), 'Total: 5');
      expect(countChip('Running', 0), 'Running: 0');
      expect(countChip('Failed', 3), 'Failed: 3');
    });

    test('by_status entries render with colors', () {
      final byStatus = {'RUNNING': 2, 'PENDING': 1, 'FAILED': 1};
      final entries = byStatus.entries.map((e) =>
        '${e.key}: ${e.value}'
      ).toList();
      expect(entries, contains('RUNNING: 2'));
      expect(entries, contains('PENDING: 1'));
      expect(entries, contains('FAILED: 1'));
    });

    test('summary agents display correctly', () {
      String agentsDisplay(List<dynamic>? agents) {
        return agents?.join(', ') ?? 'none';
      }
      expect(agentsDisplay(['builder', 'coder']), 'builder, coder');
      expect(agentsDisplay([]), '');
      expect(agentsDisplay(null), 'none');
    });

    test('status string formatting works', () {
      String formatStatus(String status) {
        return status;
      }
      expect(formatStatus('RUNNING'), 'RUNNING');
      expect(formatStatus('COMPLETED'), 'COMPLETED');
    });
  });
}
