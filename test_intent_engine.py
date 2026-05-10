# Test if issue is in library imports
try:
    print("Importing config...")
    from jarvis_os.runtime.config import JarvisConfig
    print("OK - Config imported")
    
    print("Loading config...")
    config = JarvisConfig.from_env()
    print("OK - Config loaded")
    
    print("Building intent engine...")
    from jarvis_os.core.intent_engine import build_intent_engine
    intent_engine = build_intent_engine(config)
    print(f"OK - Intent engine built: {type(intent_engine)}")
    
    print("Parsing intent...")
    intent = intent_engine.parse("what is 2+2")
    print(f"OK - Intent parsed: {intent}")
    
except Exception as e:
    import traceback
    print(f"ERROR: {e}")
    traceback.print_exc()
