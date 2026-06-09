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
import logging
import re

logger = logging.getLogger(__name__)


def find_source_upload_id(content: str) -> str | None:
    if not content:
        return None
    m = re.search(r'<!--\s*pdf_form_source\s+(\S+)\s*-->', content)
    if m:
        return m.group(1)
    return None
