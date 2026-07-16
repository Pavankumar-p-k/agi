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
from fastapi import APIRouter

router = APIRouter(prefix="/rag", tags=["rag"])

@router.get("/datasets")
async def get_datasets():
    from tools.ragflow_tool import list_datasets
    return {"datasets": await list_datasets()}

@router.post("/search")
async def search_rag(body: dict):
    from tools.ragflow_tool import ragflow_search
    return await ragflow_search(
        query=body.get("query", ""),
        dataset_ids=body.get("dataset_ids"),
        top_k=body.get("top_k", 10),
    )
