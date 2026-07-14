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

"""
DEPRECATED — re-exports from ``memory.vector_store`` and ``memory.crud_store``.
"""
import warnings

from memory.vector_store import (
    add_to_collection,
    delete_from_collection,
    get_chroma_collection,
    rebuild_collection,
    search_collection,
)

warnings.warn(
    "core.memory_vector is deprecated. Use 'memory.vector_store' instead.",
    DeprecationWarning, stacklevel=2,
)
