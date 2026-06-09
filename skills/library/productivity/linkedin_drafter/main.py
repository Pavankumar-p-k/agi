# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from skills.utils import success_response, error_response

_tone_prompts = {
    "professional": "Here's a professional take on the topic",
    "casual": "Just a quick thought on this",
    "inspiring": "Let this sink in",
}

_hashtag_sets = {
    "professional": ["#Leadership", "#Innovation", "#Growth", "#Strategy", "#Insights"],
    "casual": ["#Thoughts", "#Life", "#Learning", "#Daily", "#Vibes"],
    "inspiring": ["#Inspiration", "#Motivation", "#Mindset", "#Success", "#Purpose"],
}

_audience_tips = {
    "network": "Best posted on weekday mornings (8-10 AM) for maximum engagement",
    "recruiters": "Best posted Tuesday-Thursday, 9-11 AM to catch recruiter attention",
    "peers": "Best posted weekday afternoons (12-2 PM) for peer engagement",
}

async def linkedin_drafter(params: dict) -> dict:
    topic = params.get("topic", "").strip()
    if not topic:
        return error_response("topic is required")
    tone = params.get("tone", "professional")
    audience = params.get("audience", "network")
    length = params.get("length", "medium")
    key_points = params.get("key_points", [])

    opener = _tone_prompts.get(tone, "Here's my take")
    body_parts = [opener + f" about {topic}:\n"]

    if length == "short":
        body_parts.append(f"💡 {topic}")
        if key_points:
            body_parts.append(f"→ {key_points[0]}")
    elif length == "medium":
        body_parts.append(f"💡 {topic}\n")
        for i, kp in enumerate(key_points[:3], 1):
            body_parts.append(f"{i}. {kp}")
    else:
        body_parts.append(f"🚀 {topic}\n")
        body_parts.append("Here's what I've learned:\n")
        for i, kp in enumerate(key_points[:5], 1):
            body_parts.append(f"{i}. {kp}")
        body_parts.append("\n💬 What's your experience with this?")

    hashtags = " ".join(_hashtag_sets.get(tone, _hashtag_sets["professional"])[:3])
    body_parts.append(f"\n\n{hashtags}")
    post_body = "\n".join(body_parts)

    emoji_map = {"professional": "📊", "casual": "😊", "inspiring": "🔥"}
    emoji = emoji_map.get(tone, "💡")

    return success_response({
        "topic": topic,
        "tone": tone,
        "audience": audience,
        "length": length,
        "post": f"{emoji} {post_body}",
        "hashtags": hashtags,
        "best_posting_time": _audience_tips.get(audience, "Weekday mornings are generally best"),
        "word_count": len(post_body.split()),
    })

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest

    async def on_load(self):
        pass
