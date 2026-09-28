#!/usr/bin/env python3
"""Analyze architecture test failures."""

with open('arch_tests_output.txt', 'r', errors='replace') as f:
    content = f.read()

# Find all lines containing 'FAILED' or 'ERROR' with test paths
import re

# Pattern to find FAILED test lines
failed_pattern = re.compile(r'FAILED (.+)')
error_pattern = re.compile(r'ERROR (.+)')

failed_tests = []
error_tests = []

for line in content.split('\n'):
    m = failed_pattern.search(line)
    if m:
        failed_tests.append(m.group(1).strip())
    m = error_pattern.search(line)
    if m:
        error_tests.append(m.group(1).strip())

print(f'FAILED tests: {len(failed_tests)}')
print(f'ERROR tests: {len(error_tests)}')
print()
print('--- FAILED tests (first 30) ---')
for ft in failed_tests[:30]:
    print(ft)
print()
print('--- ERROR tests (first 15) ---')
for et in error_tests[:15]:
    print(et)

# Categorize failures
print('\n\n--- CATEGORIZATION ---')
categories = {
    'missing_module': [],
    'import_error': [],
    'missing_attribute': [],
    'type_error': [],
    'assertion_error': [],
    'attribute_error': [],
    'other': []
}

all_failures = failed_tests + error_tests
for test in all_failures:
    categorized = False
    if 'ImportError' in test or 'ModuleNotFoundError' in test:
        categories['import_error'].append(test)
        categorized = True
    elif 'AttributeError' in test:
        categories['attribute_error'].append(test)
        categorized = True
    elif 'TypeError' in test:
        categories['type_error'].append(test)
        categorized = True
    elif 'AssertionError' in test:
        categories['assertion_error'].append(test)
        categorized = True
    elif 'ModuleNotFoundError' in test:
        categories['missing_module'].append(test)
        categorized = True
    if not categorized:
        categories['other'].append(test)

for cat, tests in categories.items():
    if tests:
        print(f'{cat}: {len(tests)} tests')
        for t in tests[:3]:
            print(f'  - {t}')
        if len(tests) > 3:
            print(f'  ... and {len(tests)-3} more')