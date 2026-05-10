# SELF-REPAIR VALIDATION

- `brain/AdaptiveSelfRepair.py` now records repair confidence and executes backup/patch/test/rollback flow.
- `brain/MetaCognitionEngine.py` validates patch ids against concrete repair history and scores outcomes.
- `benchmarks/self_repair_benchmarks/test_self_repair.py` validates a real failing module patch cycle.
