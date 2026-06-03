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
