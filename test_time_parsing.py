from assistant.smart_actions import parse_time_relative
from datetime import datetime

def test_time_parsing():
    now = datetime.now()
    print(f"Current time: {now}")

    test_cases = [
        "in 5 minutes",
        "in 2 hours",
        "tomorrow",
        "tomorrow at 9am",
        "tomorrow at 3pm",
        "at 10pm"
    ]

    for tc in test_cases:
        parsed = parse_time_relative(tc)
        print(f"Input: '{tc}' -> Parsed: {parsed}")

if __name__ == "__main__":
    test_time_parsing()
