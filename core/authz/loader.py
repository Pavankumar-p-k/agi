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
from __future__ import annotations

import logging
import os

import yaml

from .engine import authz_engine
from .schema import Role, Scope

logger = logging.getLogger("jarvis.core.authz.loader")

class PolicyLoader:
    """Loads RBAC roles and policies from YAML files."""

    def __init__(self, roles_path: str = "config/roles.yaml"):
        self.roles_path = roles_path

    def load_all(self):
        """Load and register all policies."""
        if not os.path.exists(self.roles_path):
            logger.warning("[AuthZ] Roles config not found at %s, using defaults", self.roles_path)
            return

        try:
            with open(self.roles_path) as f:
                data = yaml.safe_load(f)

            if not data:
                return

            for role_name, scopes_list in data.items():
                try:
                    role = Role(role_name)
                    scopes = set()
                    for s in scopes_list:
                        try:
                            # Verify if it's a valid scope member or a valid glob pattern
                            # If it's not in the enum but has a *, we assume it's a valid pattern
                            # Otherwise we try to map to enum for validation
                            if "*" in s:
                                scopes.add(s) # Allow glob patterns
                            else:
                                scopes.add(Scope(s))
                        except ValueError:
                            logger.warning("[AuthZ] Invalid scope '%s' for role %s", s, role_name)

                    authz_engine.register_role(role, scopes)
                except ValueError:
                    logger.warning("[AuthZ] Unknown role name in config: %s", role_name)

            logger.info("[AuthZ] Declarative roles loaded [OK]")
        except Exception as e:
            logger.error("[AuthZ] Failed to load policies: %s", e)

# Global singleton
policy_loader = PolicyLoader()
