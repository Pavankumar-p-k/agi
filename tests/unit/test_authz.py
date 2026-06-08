import pytest
from core.authz import Role, Scope, AuthContext
from core.authz.engine import PolicyEngine
from core.authz.loader import PolicyLoader
from core.tools.policy import ToolPolicy, policy_engine as tool_policy_engine
from core.tools.security import is_authorized_to_execute

@pytest.fixture
def engine():
    pe = PolicyEngine()
    pe.register_role(Role.DEVELOPER, {Scope.TOOLS_EXECUTE_MEDIUM, Scope.FILES_READ})
    pe.register_role(Role.OPERATOR, {Scope.TOOLS_EXECUTE_ALL, Scope.FILES_ADMIN})
    return pe

def test_scope_covers(engine):
    assert engine._scope_covers("tools:execute:*", "tools:execute:high")
    assert engine._scope_covers("tools:execute:*", "tools:execute:low")
    assert engine._scope_covers("files:read", "files:read")
    assert not engine._scope_covers("files:read", "files:write")
    assert not engine._scope_covers("tools:execute:medium", "tools:execute:high")

def test_evaluate_role_access(engine):
    dev_ctx = AuthContext(user_id="dev_user", roles={Role.DEVELOPER}, scopes=set())
    
    assert engine.evaluate(dev_ctx, Scope.TOOLS_EXECUTE_MEDIUM)
    assert engine.evaluate(dev_ctx, Scope.FILES_READ)
    assert not engine.evaluate(dev_ctx, Scope.TOOLS_EXECUTE_HIGH)
    assert not engine.evaluate(dev_ctx, Scope.FILES_ADMIN)

def test_evaluate_admin_access(engine):
    admin_ctx = AuthContext(user_id="admin_user", roles={Role.ADMIN}, scopes=set())
    assert engine.evaluate(admin_ctx, Scope.TOOLS_EXECUTE_HIGH)
    assert engine.evaluate(admin_ctx, "any:scope:whatsoever")

def test_is_authorized_to_execute():
    # Setup tool policy
    tool_policy_engine.register(ToolPolicy(
        id="test_bash",
        name="Bash",
        required_scope="tools:execute:high"
    ))
    
    # Mock engine for security.py (which uses the singleton)
    from core.authz.engine import authz_engine
    authz_engine.register_role(Role.DEVELOPER, {Scope.TOOLS_EXECUTE_MEDIUM})
    authz_engine.register_role(Role.OPERATOR, {"tools:execute:*"})
    
    dev_ctx = AuthContext(user_id="dev", roles={Role.DEVELOPER}, scopes=set())
    op_ctx = AuthContext(user_id="op", roles={Role.OPERATOR}, scopes=set())
    
    assert not is_authorized_to_execute("test_bash", dev_ctx)
    assert is_authorized_to_execute("test_bash", op_ctx)

def test_loader():
    import os
    import yaml
    
    test_yaml = "config/test_roles.yaml"
    with open(test_yaml, "w") as f:
        yaml.dump({"analyst": ["memory:read", "tools:execute:low"]}, f)
        
    try:
        pe = PolicyEngine()
        loader = PolicyLoader(roles_path=test_yaml)
        # Manually wire loader to local engine for test
        from unittest.mock import patch
        with patch("core.authz.loader.authz_engine", pe):
            loader.load_all()
            
        analyst_ctx = AuthContext(user_id="analyst", roles={Role.ANALYST}, scopes=set())
        assert pe.evaluate(analyst_ctx, "memory:read")
        assert not pe.evaluate(analyst_ctx, "memory:write")
    finally:
        if os.path.exists(test_yaml):
            os.remove(test_yaml)
